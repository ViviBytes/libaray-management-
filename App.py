from flask import Flask, render_template, request, redirect, session, send_from_directory
import sqlite3
import os
import json
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from difflib import SequenceMatcher


import re

app = Flask(__name__)
app.secret_key = "secret"

DB_PATH = os.path.join(os.environ.get("LOCALAPPDATA", "."), "library_management.db")
LATE_FEE_PER_DAY = 5
ISSUE_PERIOD_DAYS = 15
CATEGORIES = ("Fiction", "Self-help", "Education", "Technology")
SMTP_SETTINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "smtp_settings.json")
books_data = [
("The Alchemist", "Paulo Coelho"),
("Rich Dad Poor Dad", "Robert Kiyosaki"),
("Think and Grow Rich", "Napoleon Hill"),
("Atomic Habits", "James Clear"),
("The Power of Now", "Eckhart Tolle"),
("Ikigai", "Hector Garcia"),
("The 5 AM Club", "Robin Sharma"),
("Wings of Fire", "A.P.J. Abdul Kalam"),
("The Monk Who Sold His Ferrari", "Robin Sharma"),
("You Can Win", "Shiv Khera"),
("Harry Potter and the Sorcerer's Stone", "J.K. Rowling"),
("Harry Potter and the Chamber of Secrets", "J.K. Rowling"),
("The Hobbit", "J.R.R. Tolkien"),
("The Lord of the Rings", "J.R.R. Tolkien"),
("Game of Thrones", "George R.R. Martin"),
("The Catcher in the Rye", "J.D. Salinger"),
("To Kill a Mockingbird", "Harper Lee"),
("Pride and Prejudice", "Jane Austen"),
("The Great Gatsby", "F. Scott Fitzgerald"),
("1984", "George Orwell"),
("Moby Dick", "Herman Melville"),
("War and Peace", "Leo Tolstoy"),
("Crime and Punishment", "Fyodor Dostoevsky"),
("The Brothers Karamazov", "Fyodor Dostoevsky"),
("The Odyssey", "Homer"),
("The Iliad", "Homer"),
("Brave New World", "Aldous Huxley"),
("The Kite Runner", "Khaled Hosseini"),
("A Thousand Splendid Suns", "Khaled Hosseini"),
("The Book Thief", "Markus Zusak"),
("The Fault in Our Stars", "John Green"),
("Looking for Alaska", "John Green"),
("The Hunger Games", "Suzanne Collins"),
("Catching Fire", "Suzanne Collins"),
("Mockingjay", "Suzanne Collins"),
("Twilight", "Stephenie Meyer"),
("New Moon", "Stephenie Meyer"),
("Eclipse", "Stephenie Meyer"),
("Breaking Dawn", "Stephenie Meyer"),
("The Da Vinci Code", "Dan Brown"),
("Angels and Demons", "Dan Brown"),
("Inferno", "Dan Brown"),
("Digital Fortress", "Dan Brown"),
("The Girl with the Dragon Tattoo", "Stieg Larsson"),
("Gone Girl", "Gillian Flynn"),
("The Silent Patient", "Alex Michaelides"),
("Verity", "Colleen Hoover"),
("It Ends With Us", "Colleen Hoover"),
("Reminders of Him", "Colleen Hoover"),
("Ugly Love", "Colleen Hoover"),
]

self_help_titles = {
    "The Alchemist", "Rich Dad Poor Dad", "Think and Grow Rich", "Atomic Habits",
    "The Power of Now", "Ikigai", "The 5 AM Club", "The Monk Who Sold His Ferrari", "You Can Win",
}
technology_titles = {
    "Digital Fortress",
}
education_titles = {
    "Wings of Fire",
}


def infer_category(title):
    if title in self_help_titles:
        return "Self-help"
    if title in technology_titles:
        return "Technology"
    if title in education_titles:
        return "Education"
    return "Fiction"

# DATABASE
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT, email TEXT, created_at TEXT)"
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS books(
            id INTEGER PRIMARY KEY,
            name TEXT,
            author TEXT,
            category TEXT,
            barcode TEXT,
            shelf TEXT,
            shelf_row TEXT,
            shelf_column TEXT
        )
        """
    )
    cur.execute("CREATE TABLE IF NOT EXISTS issued(id INTEGER PRIMARY KEY, user TEXT, book TEXT, due TEXT)")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS book_requests(
            id INTEGER PRIMARY KEY,
            username TEXT,
            email TEXT,
            book TEXT,
            requested_at TEXT,
            status TEXT DEFAULT 'Pending',
            notified_at TEXT,
            notify_error TEXT,
            seen_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY,
            issue_id INTEGER UNIQUE,
            username TEXT,
            amount_paid INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Unpaid',
            paid_at TEXT
        )
        """
    )

    # Migration for existing DBs where books table has no author column
    cur.execute("PRAGMA table_info(books)")
    book_cols = [row[1] for row in cur.fetchall()]
    if "author" not in book_cols:
        cur.execute("ALTER TABLE books ADD COLUMN author TEXT DEFAULT 'Unknown'")
    if "category" not in book_cols:
        cur.execute("ALTER TABLE books ADD COLUMN category TEXT DEFAULT 'Fiction'")
    if "barcode" not in book_cols:
        cur.execute("ALTER TABLE books ADD COLUMN barcode TEXT")
    if "shelf" not in book_cols:
        cur.execute("ALTER TABLE books ADD COLUMN shelf TEXT")
    if "shelf_row" not in book_cols:
        cur.execute("ALTER TABLE books ADD COLUMN shelf_row TEXT")
    if "shelf_column" not in book_cols:
        cur.execute("ALTER TABLE books ADD COLUMN shelf_column TEXT")

    # Migration for issue_date in issued table (for better tracking)
    cur.execute("PRAGMA table_info(issued)")
    issued_cols = [row[1] for row in cur.fetchall()]
    if "issue_date" not in issued_cols:
        cur.execute("ALTER TABLE issued ADD COLUMN issue_date TEXT")
        cur.execute("UPDATE issued SET issue_date = due WHERE issue_date IS NULL")
    if "status" not in issued_cols:
        cur.execute("ALTER TABLE issued ADD COLUMN status TEXT DEFAULT 'Issued'")
        cur.execute("UPDATE issued SET status = 'Issued' WHERE status IS NULL")
    if "returned_at" not in issued_cols:
        cur.execute("ALTER TABLE issued ADD COLUMN returned_at TEXT")
    if "overdue_notified" not in issued_cols:
        cur.execute("ALTER TABLE issued ADD COLUMN overdue_notified INTEGER DEFAULT 0")

    cur.execute("PRAGMA table_info(book_requests)")
    request_cols = [row[1] for row in cur.fetchall()]
    if "email" not in request_cols:
        cur.execute("ALTER TABLE book_requests ADD COLUMN email TEXT")
    if "requested_at" not in request_cols:
        cur.execute("ALTER TABLE book_requests ADD COLUMN requested_at TEXT")
        cur.execute("UPDATE book_requests SET requested_at = datetime('now') WHERE requested_at IS NULL")
    if "status" not in request_cols:
        cur.execute("ALTER TABLE book_requests ADD COLUMN status TEXT DEFAULT 'Pending'")
        cur.execute("UPDATE book_requests SET status = 'Pending' WHERE status IS NULL")
    if "notified_at" not in request_cols:
        cur.execute("ALTER TABLE book_requests ADD COLUMN notified_at TEXT")
    if "notify_error" not in request_cols:
        cur.execute("ALTER TABLE book_requests ADD COLUMN notify_error TEXT")
    if "seen_at" not in request_cols:
        cur.execute("ALTER TABLE book_requests ADD COLUMN seen_at TEXT")

    cur.execute("PRAGMA table_info(payments)")
    payment_cols = [row[1] for row in cur.fetchall()]
    if "amount_paid" not in payment_cols:
        cur.execute("ALTER TABLE payments ADD COLUMN amount_paid INTEGER DEFAULT 0")
    if "status" not in payment_cols:
        cur.execute("ALTER TABLE payments ADD COLUMN status TEXT DEFAULT 'Unpaid'")
    if "paid_at" not in payment_cols:
        cur.execute("ALTER TABLE payments ADD COLUMN paid_at TEXT")

    # Migration for created_at in users history
    cur.execute("PRAGMA table_info(users)")
    user_cols = [row[1] for row in cur.fetchall()]
    if "created_at" not in user_cols:
        cur.execute("ALTER TABLE users ADD COLUMN created_at TEXT")
        cur.execute("UPDATE users SET created_at = datetime('now') WHERE created_at IS NULL")
    if "email" not in user_cols:
        cur.execute("ALTER TABLE users ADD COLUMN email TEXT")
        cur.execute("UPDATE users SET email = username || '@example.com' WHERE email IS NULL")

    cur.execute(
        "INSERT OR IGNORE INTO users(id,username,password,email,created_at) VALUES(1,'admin','admin123','admin@library.local', datetime('now'))"
    )

    # Seed the given 50 books if missing
    for name, author in books_data:
        category = infer_category(name)
        cur.execute("SELECT id FROM books WHERE name=? AND author=?", (name, author))
        found = cur.fetchone()
        if not found:
            cur.execute("INSERT INTO books(name, author, category) VALUES(?, ?, ?)", (name, author, category))
        else:
            cur.execute(
                "UPDATE books SET category = COALESCE(NULLIF(category, ''), ?) WHERE name=? AND author=?",
                (category, name, author),
            )

    conn.commit()
    conn.close()

init_db()


def load_smtp_settings():
    settings = {
        "SMTP_HOST": os.environ.get("SMTP_HOST", "").strip(),
        "SMTP_PORT": os.environ.get("SMTP_PORT", "587").strip(),
        "SMTP_USER": os.environ.get("SMTP_USER", "").strip(),
        "SMTP_PASS": os.environ.get("SMTP_PASS", "").strip(),
        "SMTP_FROM": os.environ.get("SMTP_FROM", "").strip(),
    }

    if not os.path.exists(SMTP_SETTINGS_PATH):
        if not settings["SMTP_FROM"] and settings["SMTP_USER"]:
            settings["SMTP_FROM"] = settings["SMTP_USER"]
        return settings

    try:
        with open(SMTP_SETTINGS_PATH, "r", encoding="utf-8") as fh:
            file_settings = json.load(fh)
    except (OSError, json.JSONDecodeError):
        if not settings["SMTP_FROM"] and settings["SMTP_USER"]:
            settings["SMTP_FROM"] = settings["SMTP_USER"]
        return settings

    for key in settings:
        if not settings[key]:
            settings[key] = str(file_settings.get(key, "")).strip()

    if not settings["SMTP_FROM"] and settings["SMTP_USER"]:
        settings["SMTP_FROM"] = settings["SMTP_USER"]
    if not settings["SMTP_PORT"]:
        settings["SMTP_PORT"] = "587"
    return settings


def save_smtp_settings(settings):
    clean_settings = {
        "SMTP_HOST": settings.get("SMTP_HOST", "").strip(),
        "SMTP_PORT": settings.get("SMTP_PORT", "587").strip() or "587",
        "SMTP_USER": settings.get("SMTP_USER", "").strip(),
        "SMTP_PASS": settings.get("SMTP_PASS", "").strip(),
        "SMTP_FROM": settings.get("SMTP_FROM", "").strip(),
    }
    if not clean_settings["SMTP_FROM"] and clean_settings["SMTP_USER"]:
        clean_settings["SMTP_FROM"] = clean_settings["SMTP_USER"]
    with open(SMTP_SETTINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(clean_settings, fh, indent=2)
    return clean_settings


def send_overdue_email(to_email, username, book_name, due_date, days_late, late_fee):
    smtp_settings = load_smtp_settings()
    smtp_host = smtp_settings["SMTP_HOST"]
    smtp_port = int(smtp_settings["SMTP_PORT"])
    smtp_user = smtp_settings["SMTP_USER"]
    smtp_pass = smtp_settings["SMTP_PASS"]
    smtp_from = smtp_settings["SMTP_FROM"]

    if not (smtp_host and smtp_user and smtp_pass and smtp_from and to_email):
        return False, "Email config not set (SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_FROM)."

    msg = EmailMessage()
    msg["Subject"] = "Library Overdue Alert"
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content(
        f"Hello {username},\n\n"
        f"Your issued book '{book_name}' is overdue.\n"
        f"Due date: {due_date}\n"
        f"Overdue days: {days_late}\n"
        f"Current late fee: Rs {late_fee}\n\n"
        "Please return the book as soon as possible.\n"
        "Library Management System"
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True, "Overdue email sent."
    except Exception as exc:
        return False, f"Email send failed: {exc}"


def send_book_available_email(to_email, username, book_name):
    smtp_settings = load_smtp_settings()
    smtp_host = smtp_settings["SMTP_HOST"]
    smtp_port = int(smtp_settings["SMTP_PORT"])
    smtp_user = smtp_settings["SMTP_USER"]
    smtp_pass = smtp_settings["SMTP_PASS"]
    smtp_from = smtp_settings["SMTP_FROM"]

    if not (smtp_host and smtp_user and smtp_pass and smtp_from and to_email):
        return False, "Email config not set (SMTP_HOST/SMTP_USER/SMTP_PASS/SMTP_FROM)."

    msg = EmailMessage()
    msg["Subject"] = "Requested Book Is Available Now"
    msg["From"] = smtp_from
    msg["To"] = to_email
    msg.set_content(
        f"Hello {username},\n\n"
        f"The book '{book_name}' is available now.\n"
        "You can reach the library and take it.\n\n"
        "Library Management System"
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True, "Availability email sent."
    except Exception as exc:
        return False, f"Email send failed: {exc}"


def fetch_books_with_status(cur, q="", category=""):
    where = []
    params = []
    if q:
        like = f"%{q}%"
        where.append("(b.name LIKE ? OR b.author LIKE ? OR COALESCE(b.barcode, '') LIKE ?)")
        params.extend([like, like, like])
    if category:
        where.append("COALESCE(b.category, 'Fiction') = ?")
        params.append(category)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""

    cur.execute(
        f"""
        SELECT
            b.id,
            b.name,
            b.author,
            COALESCE(b.category, 'Fiction') AS category,
            COALESCE(b.barcode, '') AS barcode,
            CASE
                WHEN EXISTS (SELECT 1 FROM issued i WHERE i.book = b.name AND COALESCE(i.status, 'Issued') = 'Issued')
                THEN 0 ELSE 1
            END AS is_available
        FROM books b
        {where_sql}
        ORDER BY b.name
        """,
        tuple(params),
    )
    return cur.fetchall()


def admin_required():
    return session.get("user") == "admin"


def fetch_user_fee_summary(cur, username):
    cur.execute(
        """
        SELECT
            i.id,
            i.book,
            i.due,
            COALESCE(i.status, 'Issued'),
            COALESCE(p.amount_paid, 0)
        FROM issued i
        LEFT JOIN payments p ON p.issue_id = i.id
        WHERE i.user = ?
        ORDER BY i.id DESC
        """,
        (username,),
    )
    rows = cur.fetchall()
    today = datetime.now().date()
    outstanding_fees = []
    total_outstanding_fee = 0
    for row in rows:
        is_active = (row[3] == "Issued")
        due_date = datetime.strptime(row[2], "%Y-%m-%d").date()
        days_late = max((today - due_date).days, 0) if is_active else 0
        late_fee = days_late * LATE_FEE_PER_DAY
        amount_paid = int(row[4] or 0)
        due_amount = max(late_fee - amount_paid, 0)
        if due_amount > 0:
            outstanding_fees.append(
                {
                    "issue_id": row[0],
                    "book": row[1],
                    "late_fee": late_fee,
                    "amount_paid": amount_paid,
                    "due_amount": due_amount,
                }
            )
            total_outstanding_fee += due_amount
    return outstanding_fees, total_outstanding_fee


def fetch_user_payment_records(cur, username):
    cur.execute(
        """
        SELECT
            i.id,
            i.book,
            COALESCE(p.amount_paid, 0),
            COALESCE(p.status, 'Unpaid'),
            COALESCE(p.paid_at, '-')
        FROM issued i
        LEFT JOIN payments p ON p.issue_id = i.id
        WHERE i.user = ?
        ORDER BY i.id DESC
        """,
        (username,),
    )
    return cur.fetchall()


def normalize_location_value(value):
    return value.strip() if value and value.strip() else None


def build_location_view_from_row(row):
    if not row:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "author": row[2] or "Unknown",
        "category": row[3] or "Fiction",
        "barcode": row[4] or "Not available",
        "shelf": row[5] or "Not assigned",
        "shelf_row": row[6] or "Not assigned",
        "shelf_column": row[7] or "Not assigned",
    }


def clean_voice_search_text(raw_text):
    cleaned = " ".join((raw_text or "").strip().lower().split())
    cleaned = re.sub(r"[^a-z0-9\s-]", " ", cleaned)
    removable_phrases = [
        "book kaha rakha hai",
        "book kahan rakhi hai",
        "book kahan rakha hai",
        "kaha rakha hai",
        "kahan rakha hai",
        "kahan rakhi hai",
        "kaha rakhi hai",
        "where is the book",
        "where is book",
        "where is",
        "book location",
        "location of",
        "find book",
        "search book",
        "book name",
        "book ka naam",
        "book ka number",
        "barcode number",
        "barcode no",
        "barcode",
        "number",
        "its barcode",
        "it barcode",
        "give me",
        "show me",
        "mujhe batao",
        "batao",
        "please",
    ]
    for phrase in removable_phrases:
        cleaned = cleaned.replace(phrase, " ")
    return " ".join(cleaned.split())


def normalize_book_search_text(value):
    normalized = re.sub(r"[^a-z0-9\s]", " ", (value or "").strip().lower())
    return " ".join(normalized.split())


def find_book_location(cur, search_text):
    raw_query = (search_text or "").strip()
    cleaned_query = clean_voice_search_text(raw_query)
    candidates = []
    for item in (raw_query, cleaned_query):
        if item and item not in candidates:
            candidates.append(item)

    for candidate in candidates:
        cur.execute(
            """
            SELECT
                id,
                name,
                author,
                COALESCE(category, 'Fiction'),
                COALESCE(barcode, ''),
                COALESCE(shelf, ''),
                COALESCE(shelf_row, ''),
                COALESCE(shelf_column, '')
            FROM books
            WHERE barcode = ?
            """,
            (candidate,),
        )
        exact_barcode = cur.fetchone()
        if exact_barcode:
            return build_location_view_from_row(exact_barcode), candidate

    for candidate in candidates:
        like = f"%{candidate}%"
        cur.execute(
            """
            SELECT
                id,
                name,
                author,
                COALESCE(category, 'Fiction'),
                COALESCE(barcode, ''),
                COALESCE(shelf, ''),
                COALESCE(shelf_row, ''),
                COALESCE(shelf_column, '')
            FROM books
            WHERE name LIKE ? OR author LIKE ? OR COALESCE(barcode, '') LIKE ?
            ORDER BY
                CASE
                    WHEN lower(name) = lower(?) THEN 0
                    WHEN lower(author) = lower(?) THEN 1
                    WHEN lower(COALESCE(barcode, '')) = lower(?) THEN 2
                    ELSE 3
                END,
                name
            LIMIT 1
            """,
            (like, like, like, candidate, candidate, candidate),
        )
        matched = cur.fetchone()
        if matched:
            return build_location_view_from_row(matched), candidate

    normalized_candidates = [normalize_book_search_text(item) for item in candidates if item]
    normalized_candidates = [item for item in normalized_candidates if item]
    if normalized_candidates:
        cur.execute(
            """
            SELECT
                id,
                name,
                author,
                COALESCE(category, 'Fiction'),
                COALESCE(barcode, ''),
                COALESCE(shelf, ''),
                COALESCE(shelf_row, ''),
                COALESCE(shelf_column, '')
            FROM books
            """
        )
        best_row = None
        best_score = 0.0
        best_candidate = ""
        for row in cur.fetchall():
            name_norm = normalize_book_search_text(row[1])
            author_norm = normalize_book_search_text(row[2] or "")
            barcode_norm = normalize_book_search_text(row[4] or "")
            for candidate in normalized_candidates:
                name_score = SequenceMatcher(None, candidate, name_norm).ratio()
                author_score = SequenceMatcher(None, candidate, author_norm).ratio() if author_norm else 0.0
                barcode_score = SequenceMatcher(None, candidate, barcode_norm).ratio() if barcode_norm else 0.0
                token_hit = 0.0
                candidate_tokens = candidate.split()
                if candidate_tokens and all(token in name_norm for token in candidate_tokens):
                    token_hit = 0.96
                score = max(name_score, author_score, barcode_score, token_hit)
                if score > best_score:
                    best_score = score
                    best_row = row
                    best_candidate = candidate
        if best_row and best_score >= 0.62:
            return build_location_view_from_row(best_row), best_candidate

    return None, cleaned_query or raw_query


def detect_query_language(text):
    sample = (text or "").strip().lower()
    hindi_markers = (
        "kaha", "kahan", "rakha", "rakhi", "batao", "mujhe", "hai", "kaun", "kaunsi",
        "kitab", "book", "naam", "number", "shelf", "row", "column",
    )
    english_markers = (
        "where", "book", "located", "find", "search", "author", "barcode", "location",
        "shelf", "row", "column",
    )

    hindi_score = sum(1 for marker in hindi_markers if marker in sample)
    english_score = sum(1 for marker in english_markers if marker in sample)
    return "hi" if hindi_score >= english_score else "en"


def build_location_response(book, language):
    if language == "hi":
        return (
            f"{book['name']} shelf {book['shelf']}, row {book['shelf_row']}, "
            f"column {book['shelf_column']} me rakhi hai."
        )
    return (
        f"{book['name']} is placed on shelf {book['shelf']}, row {book['shelf_row']}, "
        f"column {book['shelf_column']}."
    )


def fetch_user_request_notifications(cur, username):
    cur.execute(
        """
        SELECT id, book, requested_at, notified_at, COALESCE(seen_at, '')
        FROM book_requests
        WHERE username=? AND COALESCE(status, 'Pending')='Notified'
        ORDER BY notified_at DESC, id DESC
        """,
        (username,),
    )
    rows = cur.fetchall()
    items = []
    unread = 0
    for row in rows:
        is_seen = bool(row[4])
        if not is_seen:
            unread += 1
        items.append(
            {
                "id": row[0],
                "book": row[1],
                "requested_at": row[2] or "-",
                "notified_at": row[3] or "-",
                "is_seen": is_seen,
                "message": f"{row[1]} is available now. You can borrow this book now.",
            }
        )
    return items, unread


def promote_available_requests(cur, username=None):
    params = []
    user_filter = ""
    if username:
        user_filter = "AND username=?"
        params.append(username)

    cur.execute(
        f"""
        UPDATE book_requests
        SET status='Notified', notified_at=COALESCE(notified_at, datetime('now'))
        WHERE COALESCE(status, 'Pending')='Pending'
        {user_filter}
        AND NOT EXISTS (
            SELECT 1 FROM issued i
            WHERE i.book = book_requests.book AND COALESCE(i.status, 'Issued')='Issued'
        )
        """,
        tuple(params),
    )

# HOME (public landing page)
@app.route("/", methods=["GET"])
def home():
    return render_template("index.html")

@app.route("/assets/<path:filename>")
def local_asset(filename):
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), filename)


# LOGIN
@app.route("/login", methods=["GET","POST"])
def login():
    error = None 
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username=? AND password=?", (u,p))
        user = cur.fetchone()
        conn.close()

        if user:
            session["user"] = u
            return redirect("/admin" if u=="admin" else "/home")
        error = "Invalid login ID or password."

    return render_template("login.html", error=error)

# SIGNUP
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        email = request.form.get("email", "").strip()

        if u.strip().lower() == "admin":
            return render_template("register.html", error="Admin ID is reserved. Please choose another User ID.")
        if not email or "@" not in email:
            return render_template("register.html", error="Please enter a valid email address.")

        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username=?", (u,))
        existing = cur.fetchone()
        if existing:
            conn.close()
            return render_template("register.html", error="User ID already exists. Please use another one.")
        cur.execute("SELECT id FROM users WHERE email=?", (email,))
        existing_email = cur.fetchone()
        if existing_email:
            conn.close()
            return render_template("register.html", error="Email already registered. Please use another email.")

        cur.execute(
            "INSERT INTO users(username,password,email,created_at) VALUES(?,?,?, datetime('now'))",
            (u, p, email),
        )
        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("register.html")

# DASHBOARD
@app.route("/dashboard", methods=["GET"])
def dashboard():
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    promote_available_requests(cur, session["user"])
    conn.commit()

    cur.execute(
        "SELECT id, user, book, due, issue_date, COALESCE(status, 'Issued'), returned_at, COALESCE(overdue_notified, 0) FROM issued WHERE user=? ORDER BY id DESC",
        (session["user"],),
    )
    issued = cur.fetchall()
    cur.execute("SELECT email FROM users WHERE username=?", (session["user"],))
    user_row = cur.fetchone()
    user_email = user_row[0] if user_row else ""
    today = datetime.now().date()
    notifications = []
    issued_view = []
    for item in issued:
        due_date = datetime.strptime(item[3], "%Y-%m-%d").date()
        is_active = (item[5] == "Issued")
        days_late = max((today - due_date).days, 0) if is_active else 0
        late_fee = days_late * LATE_FEE_PER_DAY
        status = "Returned" if not is_active else ("Overdue" if days_late > 0 else "On Time")
        issued_view.append({
            "id": item[0],
            "user": item[1],
            "book": item[2],
            "due": item[3],
            "issue_date": item[4] or "-",
            "returned_at": item[6] or "-",
            "days_late": days_late,
            "late_fee": late_fee,
            "status": status,
        })
        if is_active and days_late > 0:
            if item[7] == 0:
                sent, info = send_overdue_email(
                    user_email,
                    session["user"],
                    item[2],
                    item[3],
                    days_late,
                    late_fee,
                )
                if sent:
                    cur.execute("UPDATE issued SET overdue_notified = 1 WHERE id = ?", (item[0],))
                    conn.commit()
                notifications.append(
                    f"Overdue alert: {info}"
                )
            notifications.append(
                f"User ID {session['user']}: '{item[2]}' is Overdue by {days_late} day(s). Late fee: Rs {late_fee}."
            )

    request_notifications, unread_request_count = fetch_user_request_notifications(cur, session["user"])
    for item in request_notifications:
        notifications.append(item["message"])
    outstanding_fees, total_outstanding_fee = fetch_user_fee_summary(cur, session["user"])
    payment_records = fetch_user_payment_records(cur, session["user"])

    conn.close()

    return render_template(
        "dashboard.html",
        issued=issued_view,
        notifications=notifications,
        unread_request_count=unread_request_count,
        outstanding_fees=outstanding_fees,
        total_outstanding_fee=total_outstanding_fee,
        payment_records=payment_records,
    )


@app.route("/settings/payment/scan", methods=["POST"])
def pay_by_scanner():
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    outstanding_fees, total_outstanding_fee = fetch_user_fee_summary(cur, session["user"])
    if total_outstanding_fee <= 0:
        conn.close()
        return redirect("/dashboard")

    for fee in outstanding_fees:
        amount_paid = fee["amount_paid"] + fee["due_amount"]
        cur.execute(
            """
            INSERT INTO payments(issue_id, username, amount_paid, status, paid_at)
            VALUES(?, ?, ?, 'Paid', datetime('now'))
            ON CONFLICT(issue_id) DO UPDATE SET
                username=excluded.username,
                amount_paid=excluded.amount_paid,
                status='Paid',
                paid_at=datetime('now')
            """,
            (fee["issue_id"], session["user"], amount_paid),
        )
    conn.commit()
    conn.close()
    return redirect("/dashboard")


@app.route("/settings/account/delete", methods=["POST"])
def delete_own_account():
    if "user" not in session:
        return redirect("/login")
    username = session.get("user", "").strip()
    if not username or username == "admin":
        session.clear()
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM payments WHERE username=?", (username,))
    cur.execute("DELETE FROM issued WHERE user=?", (username,))
    cur.execute("DELETE FROM book_requests WHERE username=?", (username,))
    cur.execute("DELETE FROM users WHERE username=?", (username,))
    conn.commit()
    conn.close()

    session.clear()
    return redirect("/")


# USER HOME (after login)
@app.route("/home", methods=["GET", "POST"])
def user_home():
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    promote_available_requests(cur, session["user"])
    conn.commit()
    message = None
    if request.method == "POST":
        requested_book = request.form.get("request_book", "").strip()
        if requested_book:
            cur.execute("SELECT email FROM users WHERE username=?", (session["user"],))
            user_row = cur.fetchone()
            user_email = (user_row[0] if user_row else "").strip()
            cur.execute(
                "SELECT id FROM issued WHERE book=? AND COALESCE(status, 'Issued')='Issued'",
                (requested_book,),
            )
            currently_unavailable = cur.fetchone()
            cur.execute(
                """
                SELECT id
                FROM book_requests
                WHERE username=? AND book=? AND COALESCE(status, 'Pending')='Pending'
                """,
                (session["user"], requested_book),
            )
            existing_request = cur.fetchone()

            if not currently_unavailable:
                message = f"{requested_book} is already available right now."
            elif not user_email:
                message = "Your email ID is missing. Please update your account email first."
            elif existing_request:
                message = f"You have already requested {requested_book}."
            else:
                cur.execute(
                    """
                    INSERT INTO book_requests(username, email, book, requested_at, status)
                    VALUES(?,?,?, datetime('now'), 'Pending')
                    """,
                    (session["user"], user_email, requested_book),
                )
                conn.commit()
                message = f"Request saved for {requested_book}. You will get an email when it becomes available."

    q = request.args.get("q", "").strip()
    category = request.args.get("category", "").strip()
    books = fetch_books_with_status(cur, q, category)
    pending_requests = set()
    cur.execute(
        """
        SELECT book
        FROM book_requests
        WHERE username=? AND COALESCE(status, 'Pending')='Pending'
        """,
        (session["user"],),
    )
    for row in cur.fetchall():
        pending_requests.add(row[0])
    request_notifications, unread_request_count = fetch_user_request_notifications(cur, session["user"])
    conn.close()
    return render_template(
        "home.html",
        books=books,
        q=q,
        category=category,
        categories=CATEGORIES,
        total=len(books),
        message=message,
        pending_requests=pending_requests,
        unread_request_count=unread_request_count,
        username=session["user"],
    )


@app.route("/notifications")
def user_notifications():
    if "user" not in session:
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    promote_available_requests(cur, session["user"])
    conn.commit()
    notifications, unread_request_count = fetch_user_request_notifications(cur, session["user"])
    cur.execute(
        """
        UPDATE book_requests
        SET seen_at = datetime('now')
        WHERE username=? AND COALESCE(status, 'Pending')='Notified' AND seen_at IS NULL
        """,
        (session["user"],),
    )
    conn.commit()
    conn.close()
    return render_template(
        "user_notifications.html",
        notifications=notifications,
        unread_request_count=unread_request_count,
    )


@app.route("/book-location")
def user_book_location():
    if "user" not in session:
        return redirect("/login")

    query = request.args.get("query", "").strip()
    transcript = request.args.get("spoken", "").strip()
    final_query = query or transcript
    book_details = None
    matched_query = ""
    language = detect_query_language(final_query or transcript)
    response_text = ""

    if final_query:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        book_details, matched_query = find_book_location(cur, final_query)
        conn.close()
        if book_details:
            response_text = build_location_response(book_details, language)
        elif language == "hi":
            response_text = "Maaf kijiye, is search ke liye koi matching book nahi mili."
        else:
            response_text = "Sorry, I could not find a matching book for this search."

    return render_template(
        "user_book_location.html",
        query=final_query,
        spoken=transcript,
        matched_query=matched_query,
        book=book_details,
        language=language,
        response_text=response_text,
    )

# RETURN BOOK
@app.route("/return/<int:id>")
def return_book(id):
    if session.get("user") != "admin":
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT book FROM issued WHERE id=?", (id,))
    issued_row = cur.fetchone()
    cur.execute(
        "UPDATE issued SET status='Returned', returned_at=datetime('now') WHERE id=?",
        (id,),
    )
    conn.commit()

    notice = "Book marked as returned."

    if issued_row:
        book_name = issued_row[0]
        cur.execute(
            """
            SELECT id, username, email
            FROM book_requests
            WHERE book=? AND COALESCE(status, 'Pending')='Pending'
            ORDER BY requested_at, id
            """,
            (book_name,),
        )
        pending_rows = cur.fetchall()
        sent_count = 0
        failed = []
        for request_id, username, email in pending_rows:
            sent, info = send_book_available_email(email, username, book_name)
            cur.execute(
                """
                UPDATE book_requests
                SET status='Notified', notified_at=COALESCE(notified_at, datetime('now'))
                WHERE id=?
                """,
                (request_id,),
            )
            if sent:
                cur.execute(
                    """
                    UPDATE book_requests
                    SET notify_error=NULL
                    WHERE id=?
                    """,
                    (request_id,),
                )
                sent_count += 1
            else:
                cur.execute(
                    """
                    UPDATE book_requests
                    SET notify_error=?
                    WHERE id=?
                    """,
                    (info, request_id),
                )
                failed.append(f"{username}: {info}")
        conn.commit()

        if pending_rows:
            if failed and sent_count == 0:
                notice = "Return marked. In-app notifications created, but request emails failed. " + " | ".join(failed[:2])
            elif failed:
                notice = f"Return marked. In-app notifications created. {sent_count} request email(s) sent, some failed."
            else:
                notice = f"Return marked. In-app notifications created. {sent_count} request email(s) sent successfully."

    conn.close()
    return redirect(f"/admin/issues?notice={quote_plus(notice)}")

# ADMIN
@app.route("/admin", methods=["GET","POST"])
def admin():
    if not admin_required():
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM books")
    total_books = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM issued WHERE COALESCE(status, 'Issued')='Issued'")
    active_issued = cur.fetchone()[0]
    conn.close()

    return render_template(
        "admin.html",
        total_books=total_books,
        total_users=total_users,
        active_issued=active_issued,
    )


@app.route("/admin/email-settings", methods=["GET", "POST"])
def admin_email_settings():
    if not admin_required():
        return redirect("/login")

    message = None
    settings = load_smtp_settings()

    if request.method == "POST":
        action = request.form.get("action", "save").strip()
        settings = save_smtp_settings(
            {
                "SMTP_HOST": request.form.get("smtp_host", ""),
                "SMTP_PORT": request.form.get("smtp_port", "587"),
                "SMTP_USER": request.form.get("smtp_user", ""),
                "SMTP_PASS": request.form.get("smtp_pass", ""),
                "SMTP_FROM": request.form.get("smtp_from", ""),
            }
        )

        if action == "test":
            test_email = request.form.get("test_email", "").strip() or settings["SMTP_USER"]
            sent, info = send_book_available_email(test_email, "Admin", "Test Book")
            message = "Test email sent successfully." if sent else info
        else:
            message = "SMTP settings saved successfully."

    return render_template("admin_email_settings.html", settings=settings, message=message)


@app.route("/admin/books", methods=["GET", "POST"])
def admin_books():
    if not admin_required():
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if request.method == "POST":
        form_action = request.form.get("form_action", "add_book")
        if form_action == "add_book":
            book = request.form["book"].strip()
            author = request.form.get("author", "Unknown").strip() or "Unknown"
            category = request.form.get("category", "Fiction").strip() or "Fiction"
            barcode = normalize_location_value(request.form.get("barcode", ""))
            shelf = normalize_location_value(request.form.get("shelf", ""))
            shelf_row = normalize_location_value(request.form.get("shelf_row", ""))
            shelf_column = normalize_location_value(request.form.get("shelf_column", ""))
            if book:
                cur.execute(
                    """
                    INSERT INTO books(name, author, category, barcode, shelf, shelf_row, shelf_column)
                    VALUES(?,?,?,?,?,?,?)
                    """,
                    (book, author, category, barcode, shelf, shelf_row, shelf_column),
                )
                conn.commit()
        elif form_action == "update_location":
            book_id = request.form.get("book_id", "").strip()
            if book_id.isdigit():
                barcode = normalize_location_value(request.form.get("barcode", ""))
                shelf = normalize_location_value(request.form.get("shelf", ""))
                shelf_row = normalize_location_value(request.form.get("shelf_row", ""))
                shelf_column = normalize_location_value(request.form.get("shelf_column", ""))
                cur.execute(
                    """
                    UPDATE books
                    SET barcode = ?, shelf = ?, shelf_row = ?, shelf_column = ?
                    WHERE id = ?
                    """,
                    (barcode, shelf, shelf_row, shelf_column, int(book_id)),
                )
                conn.commit()

    q = request.args.get("q", "").strip()
    selected_category = request.args.get("category", "").strip()
    where = []
    params = []
    if q:
        like = f"%{q}%"
        where.append("(name LIKE ? OR author LIKE ? OR COALESCE(barcode, '') LIKE ?)")
        params.extend([like, like, like])
    if selected_category:
        where.append("COALESCE(category, 'Fiction') = ?")
        params.append(selected_category)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    cur.execute(
        f"""
        SELECT
            id,
            name,
            author,
            COALESCE(category, 'Fiction'),
            COALESCE(barcode, ''),
            COALESCE(shelf, ''),
            COALESCE(shelf_row, ''),
            COALESCE(shelf_column, '')
        FROM books
        {where_sql}
        ORDER BY id DESC
        """,
        tuple(params),
    )
    books = cur.fetchall()
    conn.close()
    return render_template("admin_books.html", books=books, q=q, category=selected_category, categories=CATEGORIES)


@app.route("/admin/book-location")
def admin_book_location():
    if not admin_required():
        return redirect("/login")

    barcode = request.args.get("barcode", "").strip()
    book_details = None

    if barcode:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        row, _ = find_book_location(cur, barcode)
        conn.close()
        if row:
            book_details = row

    return render_template("admin_book_location.html", barcode=barcode, book=book_details)


@app.route("/admin/users")
def admin_users():
    if not admin_required():
        return redirect("/login")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, created_at FROM users ORDER BY id DESC")
    users = cur.fetchall()
    conn.close()
    return render_template("admin_users.html", users=users)


@app.route("/admin/issues", methods=["GET", "POST"])
def admin_issues():
    if not admin_required():
        return redirect("/login")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    message = request.args.get("notice", "").strip() or None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        book_name = request.form.get("book", "").strip()
        if username and book_name:
            cur.execute("SELECT id FROM users WHERE username=? AND username!='admin'", (username,))
            user_exists = cur.fetchone()
            cur.execute(
                "SELECT id FROM issued WHERE book=? AND COALESCE(status, 'Issued')='Issued'",
                (book_name,),
            )
            already_issued = cur.fetchone()
            if not user_exists:
                message = "Selected user was not found."
            elif already_issued:
                message = "This book is already issued and currently not available."
            else:
                issue_date = datetime.now().date()
                due = issue_date + timedelta(days=ISSUE_PERIOD_DAYS)
                cur.execute(
                    "INSERT INTO issued(user,book,due,issue_date) VALUES(?,?,?,?)",
                    (username, book_name, due.isoformat(), issue_date.isoformat()),
                )
                conn.commit()
                message = "Book issued successfully from admin panel."

    cur.execute(
        """
        SELECT username
        FROM users
        WHERE username != 'admin'
        ORDER BY username
        """
    )
    users = [row[0] for row in cur.fetchall()]
    cur.execute(
        """
        SELECT b.name, b.author, COALESCE(b.category, 'Fiction')
        FROM books b
        WHERE NOT EXISTS (
            SELECT 1 FROM issued i
            WHERE i.book = b.name AND COALESCE(i.status, 'Issued') = 'Issued'
        )
        ORDER BY b.name
        """
    )
    available_books = cur.fetchall()
    cur.execute(
        "SELECT id, user, book, issue_date, due, COALESCE(status, 'Issued'), returned_at FROM issued ORDER BY id DESC"
    )
    issued_records = cur.fetchall()
    cur.execute(
        """
        SELECT username, email, book, requested_at, COALESCE(status, 'Pending'), COALESCE(notify_error, '')
        FROM book_requests
        ORDER BY
            CASE COALESCE(status, 'Pending')
                WHEN 'Pending' THEN 0
                ELSE 1
            END,
            requested_at DESC,
            id DESC
        """
    )
    book_requests = cur.fetchall()
    conn.close()
    return render_template(
        "admin_issues.html",
        issued_records=issued_records,
        users=users,
        available_books=available_books,
        message=message,
        book_requests=book_requests,
    )


@app.route("/admin/user/<username>")
def admin_user_detail(username):
    if not admin_required():
        return redirect("/login")
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, user, book, issue_date, due, COALESCE(status, 'Issued'), returned_at
        FROM issued
        WHERE user = ?
        ORDER BY id DESC
        """,
        (username,),
    )
    detail_rows = cur.fetchall()
    today = datetime.now().date()
    user_issue_details = []
    for row in detail_rows:
        due_date = datetime.strptime(row[4], "%Y-%m-%d").date()
        is_active = (row[5] == "Issued")
        days_late = max((today - due_date).days, 0) if is_active else 0
        late_fee = days_late * LATE_FEE_PER_DAY
        display_status = "Returned" if not is_active else ("Overdue" if days_late > 0 else "On Time")
        user_issue_details.append(
            {
                "id": row[0],
                "book": row[2],
                "issue_date": row[3] or "-",
                "due": row[4],
                "status": display_status,
                "days_late": days_late,
                "late_fee": late_fee,
                "returned_at": row[6] or "-",
            }
        )
    conn.close()
    return render_template("admin_user_detail.html", selected_user=username, user_issue_details=user_issue_details)

# DELETE BOOK
@app.route("/delete/<int:id>")
def delete(id):
    
    if not admin_required():
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM books WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect("/admin/books")

# LOGOUT
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True)
