const statusBanner = document.getElementById("status-banner");
const processBtn = document.getElementById("process-btn");
const csvInput = document.getElementById("csv-input");

const CATEGORY_LABELS = {
  bug_defect: "Bug / Defect",
  performance: "Performance",
  billing: "Billing",
  feature_request: "Feature Request",
  ux_usability: "UX / Usability",
  documentation: "Documentation",
  integration_api: "Integration / API",
  account_access: "Account / Access",
  support_experience: "Support Experience",
  other: "Other",
};

let charts = {};

const FEEDBACK_PREVIEW_LENGTH = 90;

const feedbackModal = document.getElementById("feedback-modal");
const modalItemId = document.getElementById("modal-item-id");
const modalItemText = document.getElementById("modal-item-text");
const modalCloseBtn = document.getElementById("modal-close-btn");

function openFeedbackModal(itemId, text) {
  modalItemId.textContent = itemId;
  modalItemText.textContent = text;
  feedbackModal.classList.remove("hidden");
}

function closeFeedbackModal() {
  feedbackModal.classList.add("hidden");
}

modalCloseBtn.addEventListener("click", closeFeedbackModal);
feedbackModal.addEventListener("click", (e) => {
  if (e.target === feedbackModal) closeFeedbackModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeFeedbackModal();
});

function showStatus(message, kind) {
  statusBanner.textContent = message;
  statusBanner.className = `status-banner ${kind}`;
}

function hideStatus() {
  statusBanner.className = "status-banner hidden";
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(body.detail || `Request to ${url} failed`);
  }
  return response.json();
}

function destroyChart(id) {
  if (charts[id]) {
    charts[id].destroy();
    delete charts[id];
  }
}

function renderCategoryChart(data) {
  destroyChart("category");
  const ctx = document.getElementById("category-chart");
  charts.category = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map((d) => CATEGORY_LABELS[d.category] || d.category),
      datasets: [
        {
          label: "Feedback items",
          data: data.map((d) => d.count),
          backgroundColor: "#4f46e5",
        },
      ],
    },
    options: {
      indexAxis: "y",
      plugins: { legend: { display: false }, title: { display: false } },
      scales: {
        x: { title: { display: true, text: "Number of feedback items" }, beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  });
}

function renderSentimentChart(data) {
  destroyChart("sentiment");
  const ctx = document.getElementById("sentiment-chart");
  charts.sentiment = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels: [
        `Positive (${data.positive})`,
        `Neutral (${data.neutral})`,
        `Negative (${data.negative})`,
      ],
      datasets: [
        {
          data: [data.positive, data.neutral, data.negative],
          backgroundColor: ["#12b76a", "#98a2b3", "#d92d20"],
        },
      ],
    },
    options: {
      plugins: {
        legend: { position: "bottom" },
        title: { display: true, text: `Average sentiment score: ${data.average_score}` },
      },
    },
  });
}

function renderUrgencyChart(data) {
  destroyChart("urgency");
  const ctx = document.getElementById("urgency-chart");
  const order = ["low", "medium", "high", "critical"];
  charts.urgency = new Chart(ctx, {
    type: "bar",
    data: {
      labels: order.map((k) => k[0].toUpperCase() + k.slice(1)),
      datasets: [
        {
          label: "Feedback items",
          data: order.map((k) => data[k]),
          backgroundColor: ["#12b76a", "#f79009", "#f04438", "#7a271a"],
        },
      ],
    },
    options: {
      plugins: { legend: { display: false } },
      scales: {
        y: { title: { display: true, text: "Number of feedback items" }, beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  });
}

function renderThemesChart(data) {
  destroyChart("themes");
  const ctx = document.getElementById("themes-chart");
  charts.themes = new Chart(ctx, {
    type: "bar",
    data: {
      labels: data.map((d) => d.label),
      datasets: [
        {
          label: "Items mentioning this theme",
          data: data.map((d) => d.count),
          backgroundColor: "#0e9384",
        },
      ],
    },
    options: {
      indexAxis: "y",
      plugins: { legend: { display: false } },
      scales: {
        x: { title: { display: true, text: "Number of feedback items" }, beginAtZero: true, ticks: { precision: 0 } },
      },
    },
  });
}

function renderSummary(summary) {
  document.getElementById("summary-headline").textContent = summary.headline;
  document.getElementById("narrative-text").textContent = summary.narrative_text;

  const findingsList = document.getElementById("key-findings");
  findingsList.innerHTML = "";
  summary.key_findings.forEach((f) => {
    const li = document.createElement("li");
    li.textContent = f;
    findingsList.appendChild(li);
  });

  const actionsList = document.getElementById("recommended-actions");
  actionsList.innerHTML = "";
  summary.recommended_actions.forEach((a) => {
    const li = document.createElement("li");
    li.textContent = a;
    actionsList.appendChild(li);
  });

  document.getElementById("summary-columns").classList.remove("hidden");
  document.querySelector(".empty-hint").classList.add("hidden");
}

function renderItemsTable(items) {
  const body = document.getElementById("items-table-body");
  body.innerHTML = "";

  items.forEach((item) => {
    const row = document.createElement("tr");

    const idCell = document.createElement("td");
    idCell.textContent = item.item_id;
    row.appendChild(idCell);

    const feedbackCell = document.createElement("td");
    feedbackCell.className = "feedback-cell";
    const isTruncated = item.text.length > FEEDBACK_PREVIEW_LENGTH;
    if (isTruncated) {
      feedbackCell.textContent = item.text.slice(0, FEEDBACK_PREVIEW_LENGTH).trimEnd() + "…";
      feedbackCell.classList.add("feedback-truncated");
      feedbackCell.title = "Click to read the full feedback";
      feedbackCell.addEventListener("click", () => openFeedbackModal(item.item_id, item.text));
    } else {
      feedbackCell.textContent = item.text;
    }
    row.appendChild(feedbackCell);

    const categoryCell = document.createElement("td");
    categoryCell.textContent = CATEGORY_LABELS[item.category] || item.category;
    row.appendChild(categoryCell);

    const themeCell = document.createElement("td");
    themeCell.textContent = item.themes && item.themes.length ? item.themes.join(", ") : "—";
    row.appendChild(themeCell);

    const sentimentCell = document.createElement("td");
    const sentimentPill = document.createElement("span");
    sentimentPill.className = `pill pill-${item.sentiment.label}`;
    sentimentPill.textContent = item.sentiment.label;
    sentimentCell.appendChild(sentimentPill);
    row.appendChild(sentimentCell);

    const scoreCell = document.createElement("td");
    scoreCell.textContent = item.sentiment.score.toFixed(2);
    row.appendChild(scoreCell);

    const urgencyCell = document.createElement("td");
    const urgencyPill = document.createElement("span");
    urgencyPill.className = `pill pill-${item.urgency}`;
    urgencyPill.textContent = item.urgency;
    urgencyCell.appendChild(urgencyPill);
    if (item.is_fallback) {
      const fallbackPill = document.createElement("span");
      fallbackPill.className = "pill pill-fallback";
      fallbackPill.textContent = "fallback";
      fallbackPill.title = "Classifier failed validation twice; this is a safe default record.";
      fallbackPill.style.marginLeft = "6px";
      urgencyCell.appendChild(fallbackPill);
    }
    row.appendChild(urgencyCell);

    body.appendChild(row);
  });
}

// --- Calendar / week picker ---------------------------------------------------------------
// null selectedWeek means "show the most recently processed upload" (the original behavior).
// Once a week button is clicked, every results fetch below is parameterized by ?year=&week=,
// pulling from the persisted SQLite history (core/storage.py) instead of the latest upload.
let selectedWeek = null;
let weeksData = [];

const monthSelect = document.getElementById("month-select");
const weekButtonsContainer = document.getElementById("week-buttons");
const latestUploadBtn = document.getElementById("latest-upload-btn");

function withWeekParams(url) {
  if (!selectedWeek) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}year=${selectedWeek.iso_year}&week=${selectedWeek.iso_week}`;
}

function renderWeekButtons(monthEntry) {
  weekButtonsContainer.innerHTML = "";
  if (!monthEntry) return;

  monthEntry.weeks.forEach((w) => {
    const btn = document.createElement("button");
    btn.className = "week-btn";
    btn.textContent = `Week ${w.week_number_in_month}`;
    btn.title = `${w.week_label} — ${w.item_count} item(s)`;
    if (selectedWeek && selectedWeek.iso_year === w.iso_year && selectedWeek.iso_week === w.iso_week) {
      btn.classList.add("active");
    }
    btn.addEventListener("click", () => selectWeek(w.iso_year, w.iso_week));
    weekButtonsContainer.appendChild(btn);
  });
}

function renderMonthOptions() {
  const previousValue = monthSelect.value;
  monthSelect.innerHTML = "";

  if (weeksData.length === 0) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No stored weeks yet";
    monthSelect.appendChild(opt);
    renderWeekButtons(null);
    return;
  }

  weeksData.forEach((month, idx) => {
    const opt = document.createElement("option");
    opt.value = idx;
    opt.textContent = month.month_label;
    monthSelect.appendChild(opt);
  });

  const restoredIdx = previousValue !== "" && weeksData[previousValue] ? previousValue : weeksData.length - 1;
  monthSelect.value = restoredIdx;
  renderWeekButtons(weeksData[restoredIdx]);
}

async function loadWeeksCalendar() {
  weeksData = await fetchJson("/api/weeks");
  renderMonthOptions();
}

async function selectWeek(isoYear, isoWeek) {
  selectedWeek = { iso_year: isoYear, iso_week: isoWeek };
  latestUploadBtn.classList.remove("hidden");
  renderWeekButtons(weeksData[monthSelect.value]);
  try {
    await loadAllResults();
    hideStatus();
  } catch (err) {
    showStatus(`Error: ${err.message}`, "error");
  }
}

monthSelect.addEventListener("change", () => {
  renderWeekButtons(weeksData[monthSelect.value]);
});

latestUploadBtn.addEventListener("click", async () => {
  selectedWeek = null;
  latestUploadBtn.classList.add("hidden");
  renderWeekButtons(weeksData[monthSelect.value]);
  try {
    await loadAllResults();
    hideStatus();
  } catch (err) {
    showStatus(`Error: ${err.message}`, "error");
  }
});

// --- Results loading / rendering ----------------------------------------------------------

async function loadAllResults() {
  const [categories, sentiment, urgency, themes, summary, items] = await Promise.all([
    fetchJson(withWeekParams("/api/results/categories")),
    fetchJson(withWeekParams("/api/results/sentiment")),
    fetchJson(withWeekParams("/api/results/urgency")),
    fetchJson(withWeekParams("/api/results/themes")),
    fetchJson(withWeekParams("/api/results/summary")),
    fetchJson(withWeekParams("/api/results/items")),
  ]);

  renderCategoryChart(categories);
  renderSentimentChart(sentiment);
  renderUrgencyChart(urgency);
  renderThemesChart(themes);
  renderSummary(summary);
  renderItemsTable(items);
}

processBtn.addEventListener("click", async () => {
  const file = csvInput.files[0];
  if (!file) {
    showStatus("Choose a CSV file first.", "error");
    return;
  }

  processBtn.disabled = true;
  showStatus("Processing batch — this can take a little while for larger files…", "success");

  try {
    const formData = new FormData();
    formData.append("file", file);
    const result = await fetchJson("/api/process", { method: "POST", body: formData });
    showStatus(
      `Processed ${result.processed} items (${result.rejected} rejected as unusable).`,
      "success"
    );

    // A fresh upload always shows as "latest upload," even if a specific past week was
    // selected before — the calendar refreshes in case this upload created/grew a week.
    selectedWeek = null;
    latestUploadBtn.classList.add("hidden");
    await loadWeeksCalendar();
    await loadAllResults();
  } catch (err) {
    showStatus(`Error: ${err.message}`, "error");
  } finally {
    processBtn.disabled = false;
  }
});

// If a batch was already processed earlier in this server session, show it immediately.
loadWeeksCalendar().catch(() => {});
loadAllResults().catch(() => hideStatus());
