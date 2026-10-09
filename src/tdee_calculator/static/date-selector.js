(() => {
  const date = document.getElementById("date");
  const selector = date.form;
  const entry = document.querySelector('form[action="/entries"]');
  const loadedDate = entry.elements.namedItem("entry_date").value;
  let typing = false;
  let loading = false;

  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      date.value = loadedDate;
      typing = false;
      loading = false;
    }
  });

  function loadDay() {
    if (loading || date.value === loadedDate || !date.checkValidity()) return;
    loading = true;
    selector.requestSubmit();
  }

  date.addEventListener("pointerdown", () => {
    typing = false;
  });
  date.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      date.reportValidity();
      loadDay();
    } else if (event.key !== "Tab") {
      typing = true;
    }
  });
  date.addEventListener("change", () => {
    if (!typing) loadDay();
  });
  date.addEventListener("blur", loadDay);
  entry.addEventListener("submit", (event) => {
    if (date.value !== loadedDate) {
      event.preventDefault();
      date.reportValidity();
      loadDay();
    }
  });
})();
