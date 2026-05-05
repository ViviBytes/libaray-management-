(function () {
  const micBtn = document.getElementById("voiceMicBtn");
  const voiceQuery = document.getElementById("voiceQuery");
  const spokenText = document.getElementById("spokenText");
  const voiceStatus = document.getElementById("voiceStatus");
  const voiceForm = document.getElementById("voiceSearchForm");
  const voiceOverlay = document.getElementById("voiceOverlay");
  const voiceOverlayClose = document.getElementById("voiceOverlayClose");
  const voiceOverlayCancel = document.getElementById("voiceOverlayCancel");
  const voiceOverlayStart = document.getElementById("voiceOverlayStart");
  const voiceOverlayMessage = document.getElementById("voiceOverlayMessage");
  const voiceOverlayHeard = document.getElementById("voiceOverlayHeard");
  const voiceOverlayOrb = document.getElementById("voiceOverlayOrb");
  const username = document.body.dataset.username || "User";
  let autoSubmitTimer = null;
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognition = null;
  let shouldRetryNoSpeech = false;
  let voiceAssistantOpen = false;

  if (!micBtn || !voiceQuery || !spokenText || !voiceStatus || !voiceForm) {
    return;
  }

  const setOverlayOpen = (isOpen) => {
    if (!voiceOverlay) return;
    voiceAssistantOpen = isOpen;
    voiceOverlay.classList.toggle("open", isOpen);
    voiceOverlay.setAttribute("aria-hidden", isOpen ? "false" : "true");
  };

  const setOverlayMessage = (message, heard) => {
    if (!voiceOverlayMessage || !voiceOverlayHeard) return;
    voiceOverlayMessage.textContent = message;
    voiceOverlayHeard.textContent = heard || "";
  };

  const speakText = (text, lang) => {
    if (!("speechSynthesis" in window) || !text) return null;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = lang || "en-IN";
    window.speechSynthesis.speak(utterance);
    return utterance;
  };

  const speakOverlayMessage = (message, lang, heard) => {
    setOverlayMessage(message, heard || "");
    return speakText(message, lang || "en-IN");
  };

  const submitLocator = () => {
    const value = voiceQuery.value.trim();
    if (!value) return;
    voiceForm.requestSubmit();
  };

  const closeVoiceAssistant = () => {
    shouldRetryNoSpeech = false;
    setOverlayOpen(false);
    if (voiceOverlayOrb) {
      voiceOverlayOrb.classList.remove("listening");
    }
    window.speechSynthesis.cancel();
    if (recognition) {
      try {
        recognition.stop();
      } catch (error) {
      }
    }
  };

  const startRecognition = () => {
    if (!recognition) return;
    spokenText.value = "";
    voiceQuery.value = "";
    if (voiceOverlayOrb) {
      voiceOverlayOrb.classList.add("listening");
    }
    voiceStatus.textContent = "Mic start ho raha hai...";
    setOverlayMessage("Hi " + username + ", please give me book name or its barcode number.");
    try {
      recognition.start();
    } catch (error) {
      if (voiceOverlayOrb) {
        voiceOverlayOrb.classList.remove("listening");
      }
      setOverlayMessage("Mic dobara start nahi ho pa raha. Please try again.");
    }
  };

  const openVoiceAssistant = () => {
    setOverlayOpen(true);
    if (!SpeechRecognition) {
      setOverlayMessage("Is browser me voice search support nahi hai.", "Chrome ya Edge me try kijiye.");
      return;
    }
    const greeting = "Hi " + username + ", please give me book name or its barcode number.";
    const utterance = speakOverlayMessage(greeting, "en-IN");
    if (utterance) {
      utterance.onend = () => {
        if (voiceAssistantOpen) {
          startRecognition();
        }
      };
    } else {
      window.setTimeout(() => {
        if (voiceAssistantOpen) {
          startRecognition();
        }
      }, 700);
    }
  };

  window.__openVoiceAssistant = openVoiceAssistant;

  if (!SpeechRecognition) {
    micBtn.disabled = true;
    micBtn.title = "Voice search not supported";
    voiceStatus.textContent = "Is browser me voice search support nahi hai. Aap text box se search kar sakte ho.";
  }

  if (SpeechRecognition) {
    recognition = new SpeechRecognition();
    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
      micBtn.classList.add("listening");
      if (voiceOverlayOrb) {
        voiceOverlayOrb.classList.add("listening");
      }
      voiceStatus.innerHTML = "<strong>Listening...</strong> Book name, author ya barcode bolo.";
      setOverlayMessage("Hi " + username + ", please give me book name or its barcode number.");
    };

    recognition.onresult = (event) => {
      shouldRetryNoSpeech = false;
      const transcript = event.results[0][0].transcript.trim();
      const transcriptLower = transcript.toLowerCase();
      const looksHindi = /kaha|kahan|rakha|rakhi|batao|mujhe|hai/i.test(transcript);
      const wantsPayment = /payment|pay|scanner|fine payment|fees payment/.test(transcriptLower);
      voiceQuery.value = transcript;
      spokenText.value = transcript;
      voiceStatus.innerHTML = "<strong>You said:</strong> " + transcript;

      if (wantsPayment) {
        setOverlayMessage("I heard payment command. Opening payment scanner...", transcript);
        speakText("Opening payment scanner now.", "en-IN");
        window.setTimeout(() => {
          window.location.href = "/dashboard?open_payment=1";
        }, 500);
        return;
      }

      setOverlayMessage("I heard this. Opening book location now...", transcript);
      if (transcript.length < 2) {
        voiceStatus.textContent = "Voice suna gaya, lekin clear text nahi mila. Dobara try kijiye.";
        return;
      }
      speakText(
        looksHindi ? "Aapki book location kholi ja rahi hai." : "Opening your book location now.",
        looksHindi ? "hi-IN" : "en-IN"
      );
      window.setTimeout(() => submitLocator(), 800);
    };

    recognition.onerror = (event) => {
      micBtn.classList.remove("listening");
      if (voiceOverlayOrb) {
        voiceOverlayOrb.classList.remove("listening");
      }
      if (event.error === "no-speech") {
        shouldRetryNoSpeech = true;
        voiceStatus.textContent = "Awaaz clear nahi mili. Dobara boliye.";
        speakOverlayMessage(
          "Hi " + username + ", I could not hear you clearly. Please say the book name or barcode again.",
          "en-IN"
        );
        return;
      }
      voiceStatus.textContent = "Voice error: " + event.error + ". Dobara try kijiye.";
      setOverlayMessage("Voice error: " + event.error + ". Please try again.");
    };

    recognition.onend = () => {
      micBtn.classList.remove("listening");
      if (voiceOverlayOrb) {
        voiceOverlayOrb.classList.remove("listening");
      }
      if (shouldRetryNoSpeech && voiceAssistantOpen) {
        shouldRetryNoSpeech = false;
        window.setTimeout(() => {
          if (voiceAssistantOpen) {
            startRecognition();
          }
        }, 900);
      }
    };

    micBtn.addEventListener("click", () => {
      openVoiceAssistant();
    });
  }

  if (voiceOverlayStart) {
    voiceOverlayStart.addEventListener("click", () => {
      startRecognition();
    });
  }
  if (voiceOverlayClose) {
    voiceOverlayClose.addEventListener("click", closeVoiceAssistant);
  }
  if (voiceOverlayCancel) {
    voiceOverlayCancel.addEventListener("click", closeVoiceAssistant);
  }
  if (voiceOverlay) {
    voiceOverlay.addEventListener("click", (event) => {
      if (event.target === voiceOverlay) {
        closeVoiceAssistant();
      }
    });
  }

  voiceQuery.addEventListener("input", () => {
    spokenText.value = voiceQuery.value.trim();
    if (autoSubmitTimer) {
      window.clearTimeout(autoSubmitTimer);
    }
    if (voiceQuery.value.trim().length < 2) {
      voiceStatus.textContent = "Type or speak to open the location slide automatically.";
      return;
    }
    voiceStatus.textContent = "Typing detected. Opening location slide automatically...";
    autoSubmitTimer = window.setTimeout(() => submitLocator(), 900);
  });

  voiceForm.addEventListener("submit", () => {
    if (autoSubmitTimer) {
      window.clearTimeout(autoSubmitTimer);
    }
  });
})();
