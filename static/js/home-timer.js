(function () {
  const PINK = "#e2979c";
  const RED = "#e7305b";
  const BLUE = "#18046e";
  const WORK_MIN = 1;
  const SHORT_BREAK_MIN = 5;
  const LONG_BREAK_MIN = 20;
  const pomodoroTitle = document.getElementById("pomodoroTitle");
  const pomodoroDisplay = document.getElementById("pomodoroDisplay");
  const pomodoroChecks = document.getElementById("pomodoroChecks");
  const pomodoroStart = document.getElementById("pomodoroStart");
  const pomodoroReset = document.getElementById("pomodoroReset");
  const pomodoroWidget = document.getElementById("pomodoroWidget");
  const pomodoroToggle = document.getElementById("pomodoroToggle");
  const pomodoroClose = document.getElementById("pomodoroClose");
  let reps = 0;
  let pomodoroTimer = null;

  if (!pomodoroWidget || !pomodoroDisplay || !pomodoroTitle) {
    return;
  }

  const setPomodoroOpen = (isOpen) => {
    pomodoroWidget.classList.toggle("open", isOpen);
  };

  const updatePomodoroDisplay = (count) => {
    const countMin = Math.floor(count / 60);
    const countSec = count % 60;
    pomodoroDisplay.textContent = String(countMin).padStart(2, "0") + ":" + String(countSec).padStart(2, "0");
  };

  const updateCheckMarks = () => {
    if (!pomodoroChecks) return;
    const workSessions = Math.floor(reps / 2);
    pomodoroChecks.textContent = Array(workSessions).fill("\u2713").join(" ");
  };

  const resetPomodoro = () => {
    if (pomodoroTimer) {
      window.clearTimeout(pomodoroTimer);
      pomodoroTimer = null;
    }
    reps = 0;
    pomodoroTitle.textContent = "Timer";
    pomodoroTitle.style.color = "#111827";
    if (pomodoroChecks) {
      pomodoroChecks.textContent = "";
    }
    updatePomodoroDisplay(0);
  };

  const countDown = (count) => {
    updatePomodoroDisplay(count);
    if (count > 0) {
      pomodoroTimer = window.setTimeout(() => countDown(count - 1), 1000);
      return;
    }
    pomodoroTimer = null;
    updateCheckMarks();
    startPomodoro();
  };

  function startPomodoro() {
    if (pomodoroTimer) {
      return;
    }
    reps += 1;
    const workSec = WORK_MIN * 60;
    const shortBreakSec = SHORT_BREAK_MIN * 60;
    const longBreakSec = LONG_BREAK_MIN * 60;
    if (reps % 8 === 0) {
      pomodoroTitle.textContent = "Break";
      pomodoroTitle.style.color = RED;
      countDown(longBreakSec);
    } else if (reps % 2 === 0) {
      pomodoroTitle.textContent = "Break";
      pomodoroTitle.style.color = PINK;
      countDown(shortBreakSec);
    } else {
      pomodoroTitle.textContent = "Work";
      pomodoroTitle.style.color = BLUE;
      countDown(workSec);
    }
  }

  if (pomodoroToggle) {
    pomodoroToggle.addEventListener("click", () => {
      setPomodoroOpen(!pomodoroWidget.classList.contains("open"));
    });
  }
  if (pomodoroClose) {
    pomodoroClose.addEventListener("click", () => {
      setPomodoroOpen(false);
    });
  }
  if (pomodoroStart) {
    pomodoroStart.addEventListener("click", startPomodoro);
  }
  if (pomodoroReset) {
    pomodoroReset.addEventListener("click", resetPomodoro);
  }

  resetPomodoro();
})();
