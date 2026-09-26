from flask import Flask, render_template, request, redirect, session, send_from_directory
import sqlite3
import os
import json
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from urllib.parse import quote_plus
from difflib import SequenceMatcher

from werkzeug.utils import secure_filename
import uuid
import re
import urllib.request
import urllib.parse

app = Flask(__name__)
app.secret_key = "secret"

DB_PATH = os.path.join(os.environ.get("LOCALAPPDATA", "."), "library_management.db")
COVER_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "book_covers")
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


def save_book_cover(uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        return None
    filename = secure_filename(uploaded_file.filename)
    if not filename:
        return None
    extension = os.path.splitext(filename)[1].lower()
    if extension not in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return None
    os.makedirs(COVER_FOLDER, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}{extension}"
    target_path = os.path.join(COVER_FOLDER, unique_name)
    uploaded_file.save(target_path)
    return f"book_covers/{unique_name}"


def fetch_cover_from_openlibrary(title, author):
    """Try to find a cover image via OpenLibrary search and save it locally.
    Returns relative path like 'book_covers/xxx.jpg' or None.
    """
    try:
        q_title = urllib.parse.quote_plus(title or "")
        q_author = urllib.parse.quote_plus(author or "")
        url = f"https://openlibrary.org/search.json?title={q_title}&author={q_author}&limit=1"
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.load(resp)
        docs = data.get("docs", []) if isinstance(data, dict) else []
        cover_url = None
        if docs:
            doc = docs[0]
            cover_id = doc.get("cover_i")
            if cover_id:
                cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
            else:
                isbns = doc.get("isbn") or []
                if isbns:
                    cover_url = f"https://covers.openlibrary.org/b/isbn/{urllib.parse.quote_plus(isbns[0])}-L.jpg"

        if cover_url:
            os.makedirs(COVER_FOLDER, exist_ok=True)
            ext = os.path.splitext(cover_url)[1] or ".jpg"
            unique_name = f"{uuid.uuid4().hex}{ext}"
            target_path = os.path.join(COVER_FOLDER, unique_name)
            try:
                urllib.request.urlretrieve(cover_url, target_path)
                return f"book_covers/{unique_name}"
            except Exception:
                return None
    except Exception:
        return None
    return None


@app.route('/admin/seed_books', methods=['POST'])
def admin_seed_books():
    if not admin_required():
        return redirect('/login')

    # Full curated list provided by user (will be inserted when seeding)
    seed_list = [
        ("Don Quixote", "Miguel de Cervantes"),
        ("Alice's Adventures in Wonderland", "Lewis Carroll"),
        ("The Adventures of Huckleberry Finn", "Mark Twain"),
        ("The Adventures of Tom Sawyer", "Mark Twain"),
        ("Treasure Island", "Robert Louis Stevenson"),
        ("Pride and Prejudice", "Jane Austen"),
        ("Wuthering Heights", "Emily Brontë"),
        ("Jane Eyre", "Charlotte Brontë"),
        ("Moby Dick", "Herman Melville"),
        ("The Scarlet Letter", "Nathaniel Hawthorne"),
        ("Gulliver's Travels", "Jonathan Swift"),
        ("The Pilgrim's Progress", "John Bunyan"),
        ("A Christmas Carol", "Charles Dickens"),
        ("David Copperfield", "Charles Dickens"),
        ("A Tale of Two Cities", "Charles Dickens"),
        ("Little Women", "Louisa May Alcott"),
        ("Great Expectations", "Charles Dickens"),
        ("The Hobbit, or, There and Back Again", "J.R.R. Tolkien"),
        ("Frankenstein, or, the Modern Prometheus", "Mary Shelley"),
        ("Oliver Twist", "Charles Dickens"),
        ("Uncle Tom's Cabin", "Harriet Beecher Stowe"),
        ("Crime and Punishment", "Fyodor Dostoyevsky"),
        ("Madame Bovary: Patterns of Provincial life", "Gustave Flaubert"),
        ("The Return of the King", "J.R.R. Tolkien"),
        ("Dracula", "Bram Stoker"),
        ("The Three Musketeers", "Alexandre Dumas"),
        ("Brave New World", "Aldous Huxley"),
        ("War and Peace", "Leo Tolstoy"),
        ("To Kill a Mockingbird", "Harper Lee"),
        ("The Wizard of Oz", "L. Frank Baum"),
        ("Les Misérables", "Victor Hugo"),
        ("The Secret Garden", "Frances Hodgson Burnett"),
        ("Animal Farm", "George Orwell"),
        ("The Great Gatsby", "F. Scott Fitzgerald"),
        ("The Little Prince", "Antoine de Saint-Exupéry"),
        ("The Call of the Wild", "Jack London"),
        ("20,000 Leagues Under the Sea", "Jules Verne"),
        ("Anna Karenina", "Leo Tolstoy"),
        ("The Wind in the Willows", "Kenneth Grahame"),
        ("The Picture of Dorian Gray", "Oscar Wilde"),
        ("The Grapes of Wrath", "John Steinbeck"),
        ("Sense and Sensibility", "Jane Austen"),
        ("The Last of the Mohicans", "James Fenimore Cooper"),
        ("Tess of the d'Urbervilles", "Thomas Hardy"),
        ("Harry Potter and the Sorcerer's Stone", "J.K. Rowling"),
        ("Heidi", "Johanna Spyri"),
        ("Ulysses", "James Joyce"),
        ("The Complete Sherlock Holmes", "Arthur Conan Doyle"),
        ("The Count of Monte Cristo", "Alexandre Dumas"),
        ("The Old Man and the Sea", "Ernest Hemingway"),
        ("The Lion, the Witch, and the Wardrobe", "C.S. Lewis"),
        ("The Hunchback of Notre Dame", "Victor Hugo"),
        ("Pinocchio", "Carlo Collodi"),
        ("One Hundred Years of Solitude", "Gabriel García Márquez"),
        ("Ivanhoe", "Walter Scott"),
        ("The Red Badge of Courage", "Stephen Crane"),
        ("Anne of Green Gables", "L.M. Montgomery"),
        ("Black Beauty", "Anna Sewell"),
        ("Peter Pan", "J.M. Barrie"),
        ("A Farewell to Arms", "Ernest Hemingway"),
        ("The House of the Seven Gables", "Nathaniel Hawthorne"),
        ("Lord of the Flies", "William Golding"),
        ("The Prince and the Pauper", "Mark Twain"),
        ("A Portrait of the Artist as a Young Man", "James Joyce"),
        ("Lord Jim", "Joseph Conrad"),
        ("Harry Potter and the Chamber of Secrets", "J.K. Rowling"),
        ("The Red & the Black", "Stendhal"),
        ("The Stranger", "Albert Camus"),
        ("The Trial", "Franz Kafka"),
        ("Lady Chatterley's Lover", "D.H. Lawrence"),
        ("Kidnapped: The Adventures of David Balfour", "Robert Louis Stevenson"),
        ("The Catcher in the Rye", "J.D. Salinger"),
        ("Fahrenheit 451", "Ray Bradbury"),
        ("A Journey to the Center of the Earth", "Jules Verne"),
        ("Vanity Fair", "William Makepeace Thackeray"),
        ("All Quiet on the Western Front", "Erich Maria Remarque"),
        ("Gone with the Wind", "Margaret Mitchell"),
        ("My Ántonia", "Willa Cather"),
        ("Of Mice and Men", "John Steinbeck"),
        ("The Vicar of Wakefield", "Oliver Goldsmith"),
        ("A Connecticut Yankee in King Arthur's Court", "Mark Twain"),
        ("White Fang", "Jack London"),
        ("Fathers and Sons", "Ivan Sergeevich Turgenev"),
        ("Doctor Zhivago", "Boris Leonidovich Pasternak"),
        ("The Decameron", "Giovanni Boccaccio"),
        ("Nineteen Eighty-Four", "George Orwell"),
        ("The Jungle", "Upton Sinclair"),
        ("The Da Vinci Code", "Dan Brown"),
        ("Persuasion", "Jane Austen"),
        ("Mansfield Park", "Jane Austen"),
        ("Candide", "Voltaire"),
        ("For Whom the Bell Tolls", "Ernest Hemingway"),
        ("Far from the Madding Crowd", "Thomas Hardy"),
        ("The Fellowship of the Ring", "J.R.R. Tolkien"),
        ("The Return of the Native", "Thomas Hardy"),
        ("Sons and Lovers", "D.H. Lawrence"),
        ("Charlotte's Web", "E.B. White"),
        ("The Swiss Family Robinson", "Johann David Wyss"),
        ("Bleak House", "Charles Dickens"),
        ("Père Goriot", "Honoré de Balzac"),
        ("Utopia", "Thomas More"),
        ("The History of Tom Jones, a Foundling", "Henry Fielding"),
        ("Harry Potter and the Prisoner of Azkaban", "J.K. Rowling"),
        ("Kim", "Rudyard Kipling"),
        ("The Sound and the Fury", "William Faulkner"),
        ("Harry Potter and the Goblet of Fire", "J.K. Rowling"),
        ("The Mill on the Floss", "George Eliot"),
        ("A Wrinkle in Time", "Madeleine L'Engle"),
        ("The Hound of the Baskervilles", "Arthur Conan Doyle"),
        ("The Two Towers", "J.R.R. Tolkien"),
        ("The War of the Worlds", "H.G. Wells"),
        ("Middlemarch", "George Eliot"),
        ("The Age of Innocence", "Edith Wharton"),
        ("The Color Purple", "Alice Walker"),
        ("Northanger Abbey", "Jane Austen"),
        ("East of Eden", "John Steinbeck"),
        ("On the Road", "Jack Kerouac"),
        ("Catch-22", "Joseph Heller"),
        ("Around the World in Eighty Days", "Jules Verne"),
        ("Hard Times", "Charles Dickens"),
        ("Beloved", "Toni Morrison"),
        ("Mrs. Dalloway", "Virginia Woolf"),
        ("To the Lighthouse", "Virginia Woolf"),
        ("The Magician's Nephew", "C.S. Lewis"),
        ("Harry Potter and the Order of the Phoenix", "J.K. Rowling"),
        ("The Sun Also Rises", "Ernest Hemingway"),
        ("The Good Earth", "Pearl S. Buck"),
        ("Silas Marner", "George Eliot"),
        ("Love in the Time of Cholera", "Gabriel García Márquez"),
        ("Rebecca", "Daphne Du Maurier"),
        ("Jude the Obscure", "Thomas Hardy"),
        ("Twilight", "Stephenie Meyer"),
        ("A Passage to India", "E.M. Forster"),
        ("The Plague", "Albert Camus"),
        ("Nicholas Nickleby", "Charles Dickens"),
        ("The Pearl", "John Steinbeck"),
        ("Ethan Frome", "Edith Wharton"),
        ("The Tale of Genji", "Murasaki Shikibu"),
        ("The Giver", "Lois Lowry"),
        ("The Alchemist", "Paulo Coelho"),
        ("The Strange Case of Dr. Jekyll and Mr. Hyde", "Robert Louis Stevenson"),
        ("Robinson Crusoe", "Daniel Defoe"),
        ("Tender is the Night", "F. Scott Fitzgerald"),
        ("The Idiot", "Fyodor Dostoyevsky"),
        ("Hatchet", "Gary Paulsen"),
        ("The Kite Runner", "Khaled Hosseini"),
        ("One Flew Over the Cuckoo's Nest", "Ken Kesey"),
        ("The Portrait of a Lady", "Henry James"),
        ("The Outsiders", "S.E. Hinton"),
        ("Ben-Hur", "Lew Wallace"),
        ("The Mayor of Casterbridge", "Thomas Hardy"),
        ("Cry, The Beloved Country", "Alan Paton"),
        ("The Last Battle", "C.S. Lewis"),
        ("Captains Courageous", "Rudyard Kipling"),
        ("The Castle", "Franz Kafka"),
        ("The Metamorphosis", "Franz Kafka"),
        ("The Magic Mountain (Der Zauberberg)", "Thomas Mann"),
        ("James and the Giant Peach", "Roald Dahl"),
        ("The Horse and His Boy", "C.S. Lewis"),
        ("Angels &amp; Demons", "Dan Brown"),
        ("The Voyage of the Dawn Treader", "C.S. Lewis"),
        ("The Bell Jar", "Sylvia Plath"),
        ("Women in Love", "D.H. Lawrence"),
        ("The Yearling", "Marjorie Kinnan Rawlings"),
        ("O Pioneers!", "Willa Cather"),
        ("The Handmaid's Tale", "Margaret Atwood"),
        ("The Moonstone", "Wilkie Collins"),
        ("The Old Curiosity Shop", "Charles Dickens"),
        ("Little Dorrit", "Charles Dickens"),
        ("Prince Caspian: The Return to Narnia", "C.S. Lewis"),
        ("Sister Carrie", "Theodore Dreiser"),
        ("The Silver Chair", "C.S. Lewis"),
        ("The Hunger Games", "Suzanne Collins"),
        ("This Side of Paradise", "F. Scott Fitzgerald"),
        ("Eugénie Grandet", "Honoré de Balzac"),
        ("Of Human Bondage", "W. Somerset Maugham"),
        ("Dream of the Red Chamber", "Cao Xueqin"),
        ("Life of Pi", "Yann Martel"),
        ("Harry Potter and the Deathly Hallows", "J.K. Rowling"),
        ("Invisible Man", "Ralph Ellison"),
        ("Steppenwolf", "Hermann Hesse"),
        ("The Sorrows of Young Werther", "Johann Wolfgang von Goethe"),
        ("Bridge to Terabithia", "Katherine Paterson"),
        ("The Invisible Man", "H.G. Wells"),
        ("Holes", "Louis Sachar"),
        ("Siddhartha", "Hermann Hesse"),
        ("A Tree Grows in Brooklyn", "Betty Smith"),
        ("Through the Looking-Glass, and What Alice Found There", "Lewis Carroll"),
        ("In Cold Blood", "Truman Capote"),
        ("The House of the Spirits", "Isabel Allende"),
        ("Adam Bede", "George Eliot"),
        ("The Betrothed", "Alessandro Manzoni"),
        ("The Book Thief", "Markus Zusak"),
        ("Their Eyes Were Watching God", "Zora Neale Hurston"),
        ("One Day in the Life of Ivan Denisovich", "Aleksandr Isaevich Solzhenitsyn"),
        ("The Sea Wolf", "Jack London"),
        ("Catching Fire", "Suzanne Collins"),
        ("Roll of Thunder, Hear My Cry", "Mildred D. Taylor"),
        ("Death Comes for the Archbishop", "Willa Cather"),
        ("The House of Mirth", "Edith Wharton"),
        ("Light in August", "William Faulkner"),
        ("The Pickwick Papers", "Charles Dickens"),
        ("Remembrance of Things Past", "Marcel Proust"),
        ("Barchester Towers and the Warden", "Anthony Trollope"),
        ("The Bridge of San Luis Rey", "Thornton Wilder"),
        ("The Help", "Kathryn Stockett"),
        ("Murder on the Orient Express", "Agatha Christie"),
        ("The Lovely Bones", "Alice Sebold"),
        ("The Appeal", "John Grisham"),
        ("Dombey And Son", "Charles Dickens"),
        ("Slaughterhouse-Five", "Kurt Vonnegut"),
        ("An American Tragedy", "Theodore Dreiser"),
        ("The Bluest Eye", "Toni Morrison"),
        ("Little House In the Big Woods", "Laura Ingalls Wilder"),
        ("Pippi Longstocking", "Astrid Lindgren"),
        ("Germinal", "Émile Zola"),
        ("The Heart Is a Lonely Hunter", "Carson McCullers"),
        ("The Woman In White", "Wilkie Collins"),
        ("Absalom, Absalom!", "William Faulkner"),
        ("A Painted House", "John Grisham"),
        ("The Girl With the Dragon Tattoo", "Stieg Larsson"),
        ("A Room With a View", "E.M. Forster"),
        ("Watership Down", "Richard Adams"),
        ("Memoirs of a Geisha", "Arthur Golden"),
        ("Our Mutual Friend", "Charles Dickens"),
        ("Babbitt", "Sinclair Lewis"),
        ("The Red Pony", "John Steinbeck"),
    ]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    # Remove existing books
    cur.execute("DELETE FROM books")
    conn.commit()

    for name, author in seed_list:
        category = infer_category(name)
        cover = fetch_cover_from_openlibrary(name, author)
        cur.execute(
            "INSERT INTO books(name, author, category, cover_image) VALUES(?,?,?,?)",
            (name, author, category, cover),
        )
        conn.commit()

    conn.close()
    return redirect('/admin?notice=' + quote_plus('Seeded books and downloaded available covers.'))


def seed_books_now():
    """Non-route helper to seed the DB immediately. Returns number of books inserted."""
    seed_list = [
        ("Don Quixote", "Miguel de Cervantes"),
        ("Alice's Adventures in Wonderland", "Lewis Carroll"),
        ("The Adventures of Huckleberry Finn", "Mark Twain"),
        ("The Adventures of Tom Sawyer", "Mark Twain"),
        ("Treasure Island", "Robert Louis Stevenson"),
        ("Pride and Prejudice", "Jane Austen"),
        ("Wuthering Heights", "Emily Brontë"),
        ("Jane Eyre", "Charlotte Brontë"),
        ("Moby Dick", "Herman Melville"),
        ("The Scarlet Letter", "Nathaniel Hawthorne"),
        ("Gulliver's Travels", "Jonathan Swift"),
        ("The Pilgrim's Progress", "John Bunyan"),
        ("A Christmas Carol", "Charles Dickens"),
        ("David Copperfield", "Charles Dickens"),
        ("A Tale of Two Cities", "Charles Dickens"),
        ("Little Women", "Louisa May Alcott"),
        ("Great Expectations", "Charles Dickens"),
        ("The Hobbit, or, There and Back Again", "J.R.R. Tolkien"),
        ("Frankenstein, or, the Modern Prometheus", "Mary Shelley"),
        ("Oliver Twist", "Charles Dickens"),
        ("Uncle Tom's Cabin", "Harriet Beecher Stowe"),
        ("Crime and Punishment", "Fyodor Dostoyevsky"),
        ("Madame Bovary: Patterns of Provincial life", "Gustave Flaubert"),
        ("The Return of the King", "J.R.R. Tolkien"),
        ("Dracula", "Bram Stoker"),
        ("The Three Musketeers", "Alexandre Dumas"),
        ("Brave New World", "Aldous Huxley"),
        ("War and Peace", "Leo Tolstoy"),
        ("To Kill a Mockingbird", "Harper Lee"),
        ("The Wizard of Oz", "L. Frank Baum"),
        ("Les Misérables", "Victor Hugo"),
        ("The Secret Garden", "Frances Hodgson Burnett"),
        ("Animal Farm", "George Orwell"),
        ("The Great Gatsby", "F. Scott Fitzgerald"),
        ("The Little Prince", "Antoine de Saint-Exupéry"),
        ("The Call of the Wild", "Jack London"),
        ("20,000 Leagues Under the Sea", "Jules Verne"),
        ("Anna Karenina", "Leo Tolstoy"),
        ("The Wind in the Willows", "Kenneth Grahame"),
        ("The Picture of Dorian Gray", "Oscar Wilde"),
        ("The Grapes of Wrath", "John Steinbeck"),
        ("Sense and Sensibility", "Jane Austen"),
        ("The Last of the Mohicans", "James Fenimore Cooper"),
        ("Tess of the d'Urbervilles", "Thomas Hardy"),
        ("Harry Potter and the Sorcerer's Stone", "J.K. Rowling"),
        ("Heidi", "Johanna Spyri"),
        ("Ulysses", "James Joyce"),
        ("The Complete Sherlock Holmes", "Arthur Conan Doyle"),
        ("The Count of Monte Cristo", "Alexandre Dumas"),
        ("The Old Man and the Sea", "Ernest Hemingway"),
        ("The Lion, the Witch, and the Wardrobe", "C.S. Lewis"),
        ("The Hunchback of Notre Dame", "Victor Hugo"),
        ("Pinocchio", "Carlo Collodi"),
        ("One Hundred Years of Solitude", "Gabriel García Márquez"),
        ("Ivanhoe", "Walter Scott"),
        ("The Red Badge of Courage", "Stephen Crane"),
        ("Anne of Green Gables", "L.M. Montgomery"),
        ("Black Beauty", "Anna Sewell"),
        ("Peter Pan", "J.M. Barrie"),
        ("A Farewell to Arms", "Ernest Hemingway"),
        ("The House of the Seven Gables", "Nathaniel Hawthorne"),
        ("Lord of the Flies", "William Golding"),
        ("The Prince and the Pauper", "Mark Twain"),
        ("A Portrait of the Artist as a Young Man", "James Joyce"),
        ("Lord Jim", "Joseph Conrad"),
        ("Harry Potter and the Chamber of Secrets", "J.K. Rowling"),
        ("The Red & the Black", "Stendhal"),
        ("The Stranger", "Albert Camus"),
        ("The Trial", "Franz Kafka"),
        ("Lady Chatterley's Lover", "D.H. Lawrence"),
        ("Kidnapped: The Adventures of David Balfour", "Robert Louis Stevenson"),
        ("The Catcher in the Rye", "J.D. Salinger"),
        ("Fahrenheit 451", "Ray Bradbury"),
        ("A Journey to the Center of the Earth", "Jules Verne"),
        ("Vanity Fair", "William Makepeace Thackeray"),
        ("All Quiet on the Western Front", "Erich Maria Remarque"),
        ("Gone with the Wind", "Margaret Mitchell"),
        ("My Ántonia", "Willa Cather"),
        ("Of Mice and Men", "John Steinbeck"),
        ("The Vicar of Wakefield", "Oliver Goldsmith"),
        ("A Connecticut Yankee in King Arthur's Court", "Mark Twain"),
        ("White Fang", "Jack London"),
        ("Fathers and Sons", "Ivan Sergeevich Turgenev"),
        ("Doctor Zhivago", "Boris Leonidovich Pasternak"),
        ("The Decameron", "Giovanni Boccaccio"),
        ("Nineteen Eighty-Four", "George Orwell"),
        ("The Jungle", "Upton Sinclair"),
        ("The Da Vinci Code", "Dan Brown"),
        ("Persuasion", "Jane Austen"),
        ("Mansfield Park", "Jane Austen"),
        ("Candide", "Voltaire"),
        ("For Whom the Bell Tolls", "Ernest Hemingway"),
        ("Far from the Madding Crowd", "Thomas Hardy"),
        ("The Fellowship of the Ring", "J.R.R. Tolkien"),
        ("The Return of the Native", "Thomas Hardy"),
        ("Sons and Lovers", "D.H. Lawrence"),
        ("Charlotte's Web", "E.B. White"),
        ("The Swiss Family Robinson", "Johann David Wyss"),
        ("Bleak House", "Charles Dickens"),
        ("Père Goriot", "Honoré de Balzac"),
        ("Utopia", "Thomas More"),
        ("The History of Tom Jones, a Foundling", "Henry Fielding"),
        ("Harry Potter and the Prisoner of Azkaban", "J.K. Rowling"),
        ("Kim", "Rudyard Kipling"),
        ("The Sound and the Fury", "William Faulkner"),
        ("Harry Potter and the Goblet of Fire", "J.K. Rowling"),
        ("The Mill on the Floss", "George Eliot"),
        ("A Wrinkle in Time", "Madeleine L'Engle"),
        ("The Hound of the Baskervilles", "Arthur Conan Doyle"),
        ("The Two Towers", "J.R.R. Tolkien"),
        ("The War of the Worlds", "H.G. Wells"),
        ("Middlemarch", "George Eliot"),
        ("The Age of Innocence", "Edith Wharton"),
        ("The Color Purple", "Alice Walker"),
        ("Northanger Abbey", "Jane Austen"),
        ("East of Eden", "John Steinbeck"),
        ("On the Road", "Jack Kerouac"),
        ("Catch-22", "Joseph Heller"),
        ("Around the World in Eighty Days", "Jules Verne"),
        ("Hard Times", "Charles Dickens"),
        ("Beloved", "Toni Morrison"),
        ("Mrs. Dalloway", "Virginia Woolf"),
        ("To the Lighthouse", "Virginia Woolf"),
        ("The Magician's Nephew", "C.S. Lewis"),
        ("Harry Potter and the Order of the Phoenix", "J.K. Rowling"),
        ("The Sun Also Rises", "Ernest Hemingway"),
        ("The Good Earth", "Pearl S. Buck"),
        ("Silas Marner", "George Eliot"),
        ("Love in the Time of Cholera", "Gabriel García Márquez"),
        ("Rebecca", "Daphne Du Maurier"),
        ("Jude the Obscure", "Thomas Hardy"),
        ("Twilight", "Stephenie Meyer"),
        ("A Passage to India", "E.M. Forster"),
        ("The Plague", "Albert Camus"),
        ("Nicholas Nickleby", "Charles Dickens"),
        ("The Pearl", "John Steinbeck"),
        ("Ethan Frome", "Edith Wharton"),
        ("The Tale of Genji", "Murasaki Shikibu"),
        ("The Giver", "Lois Lowry"),
        ("The Alchemist", "Paulo Coelho"),
        ("The Strange Case of Dr. Jekyll and Mr. Hyde", "Robert Louis Stevenson"),
        ("Robinson Crusoe", "Daniel Defoe"),
        ("Tender is the Night", "F. Scott Fitzgerald"),
        ("The Idiot", "Fyodor Dostoyevsky"),
        ("Hatchet", "Gary Paulsen"),
        ("The Kite Runner", "Khaled Hosseini"),
        ("One Flew Over the Cuckoo's Nest", "Ken Kesey"),
        ("The Portrait of a Lady", "Henry James"),
        ("The Outsiders", "S.E. Hinton"),
        ("Ben-Hur", "Lew Wallace"),
        ("The Mayor of Casterbridge", "Thomas Hardy"),
        ("Cry, The Beloved Country", "Alan Paton"),
        ("The Last Battle", "C.S. Lewis"),
        ("Captains Courageous", "Rudyard Kipling"),
        ("The Castle", "Franz Kafka"),
        ("The Metamorphosis", "Franz Kafka"),
        ("The Magic Mountain (Der Zauberberg)", "Thomas Mann"),
        ("James and the Giant Peach", "Roald Dahl"),
        ("The Horse and His Boy", "C.S. Lewis"),
        ("Angels &amp; Demons", "Dan Brown"),
        ("The Voyage of the Dawn Treader", "C.S. Lewis"),
        ("The Bell Jar", "Sylvia Plath"),
        ("Women in Love", "D.H. Lawrence"),
        ("The Yearling", "Marjorie Kinnan Rawlings"),
        ("O Pioneers!", "Willa Cather"),
        ("The Handmaid's Tale", "Margaret Atwood"),
        ("The Moonstone", "Wilkie Collins"),
        ("The Old Curiosity Shop", "Charles Dickens"),
        ("Little Dorrit", "Charles Dickens"),
        ("Prince Caspian: The Return to Narnia", "C.S. Lewis"),
        ("Sister Carrie", "Theodore Dreiser"),
        ("The Silver Chair", "C.S. Lewis"),
        ("The Hunger Games", "Suzanne Collins"),
        ("This Side of Paradise", "F. Scott Fitzgerald"),
        ("Eugénie Grandet", "Honoré de Balzac"),
        ("Of Human Bondage", "W. Somerset Maugham"),
        ("Dream of the Red Chamber", "Cao Xueqin"),
        ("Life of Pi", "Yann Martel"),
        ("Harry Potter and the Deathly Hallows", "J.K. Rowling"),
        ("Invisible Man", "Ralph Ellison"),
        ("Steppenwolf", "Hermann Hesse"),
        ("The Sorrows of Young Werther", "Johann Wolfgang von Goethe"),
        ("Bridge to Terabithia", "Katherine Paterson"),
        ("The Invisible Man", "H.G. Wells"),
        ("Holes", "Louis Sachar"),
        ("Siddhartha", "Hermann Hesse"),
        ("A Tree Grows in Brooklyn", "Betty Smith"),
        ("Through the Looking-Glass, and What Alice Found There", "Lewis Carroll"),
        ("In Cold Blood", "Truman Capote"),
        ("The House of the Spirits", "Isabel Allende"),
        ("Adam Bede", "George Eliot"),
        ("The Betrothed", "Alessandro Manzoni"),
        ("The Book Thief", "Markus Zusak"),
        ("Their Eyes Were Watching God", "Zora Neale Hurston"),
        ("One Day in the Life of Ivan Denisovich", "Aleksandr Isaevich Solzhenitsyn"),
        ("The Sea Wolf", "Jack London"),
        ("Catching Fire", "Suzanne Collins"),
        ("Roll of Thunder, Hear My Cry", "Mildred D. Taylor"),
        ("Death Comes for the Archbishop", "Willa Cather"),
        ("The House of Mirth", "Edith Wharton"),
        ("Light in August", "William Faulkner"),
        ("The Pickwick Papers", "Charles Dickens"),
        ("Remembrance of Things Past", "Marcel Proust"),
        ("Barchester Towers and the Warden", "Anthony Trollope"),
        ("The Bridge of San Luis Rey", "Thornton Wilder"),
        ("The Help", "Kathryn Stockett"),
        ("Murder on the Orient Express", "Agatha Christie"),
        ("The Lovely Bones", "Alice Sebold"),
        ("The Appeal", "John Grisham"),
        ("Dombey And Son", "Charles Dickens"),
        ("Slaughterhouse-Five", "Kurt Vonnegut"),
        ("An American Tragedy", "Theodore Dreiser"),
        ("The Bluest Eye", "Toni Morrison"),
        ("Little House In the Big Woods", "Laura Ingalls Wilder"),
        ("Pippi Longstocking", "Astrid Lindgren"),
        ("Germinal", "Émile Zola"),
        ("The Heart Is a Lonely Hunter", "Carson McCullers"),
        ("The Woman In White", "Wilkie Collins"),
        ("Absalom, Absalom!", "William Faulkner"),
        ("A Painted House", "John Grisham"),
        ("The Girl With the Dragon Tattoo", "Stieg Larsson"),
        ("A Room With a View", "E.M. Forster"),
        ("Watership Down", "Richard Adams"),
        ("Memoirs of a Geisha", "Arthur Golden"),
        ("Our Mutual Friend", "Charles Dickens"),
        ("Babbitt", "Sinclair Lewis"),
        ("The Red Pony", "John Steinbeck"),
    ]

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM books")
    conn.commit()
    count = 0
    for name, author in seed_list:
        category = infer_category(name)
        cover = fetch_cover_from_openlibrary(name, author)
        cur.execute(
            "INSERT INTO books(name, author, category, cover_image) VALUES(?,?,?,?)",
            (name, author, category, cover),
        )
        conn.commit()
        count += 1
    conn.close()
    return count

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
            shelf_column TEXT,
            cover_image TEXT
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
    if "cover_image" not in book_cols:
        cur.execute("ALTER TABLE books ADD COLUMN cover_image TEXT")

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

    # Seed the given 50 books if missing, but do not fetch remote cover images during startup.
    for name, author in books_data:
        category = infer_category(name)
        cur.execute("SELECT id FROM books WHERE name=? AND author=?", (name, author))
        found = cur.fetchone()
        if not found:
            cur.execute(
                "INSERT INTO books(name, author, category, cover_image) VALUES(?, ?, ?, ?)",
                (name, author, category, ""),
            )
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
            END AS is_available,
            COALESCE(b.cover_image, '') AS cover_image
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
        "cover_image": row[8] or "",
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
                COALESCE(shelf_column, ''),
                COALESCE(cover_image, '')
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
                COALESCE(shelf_column, ''),
                COALESCE(cover_image, '')
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
                COALESCE(shelf_column, ''),
                COALESCE(cover_image, '')
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
            cover_image = save_book_cover(request.files.get("cover_image"))
            if not cover_image:
                cover_image = fetch_cover_from_openlibrary(book, author)
            if book:
                cur.execute(
                    """
                    INSERT INTO books(name, author, category, barcode, shelf, shelf_row, shelf_column, cover_image)
                    VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (book, author, category, barcode, shelf, shelf_row, shelf_column, cover_image),
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
            COALESCE(shelf_column, ''),
            COALESCE(cover_image, '')
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


@app.route("/robots.txt")
def robots():
    return app.send_static_file("robots.txt")


@app.route("/sitemap.xml")
def sitemap():
    return app.send_static_file("sitemap.xml")


if __name__ == "__main__":
    import sys
    if "--seed" in sys.argv:
        try:
            count = seed_books_now()
            report_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed_report_local.txt")
            with open(report_path, "w", encoding="utf-8") as fh:
                fh.write(f"seeded_count={count}\n")
            print(f"Seeded {count} books (report: {report_path})")
        except Exception as e:
            print("Seeding failed:", e)
        sys.exit(0)

    app.run(host="127.0.0.1", port=5000, debug=True)
