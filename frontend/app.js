const state = { courses: [], categories: {}, programs: [], selectedProgram: "cpp-cs-bs", selectedPrograms: [], programTotalUnits: 0, ge: null, geEnabled: false, user: null, authMode: "login", terms: [], search: "", category: "all" };
const API_BASE = window.location.port === "5500" ? "http://localhost:8010" : "";
const CURRENT_PAGE = document.body.dataset.page || "terms";
const $ = (selector) => document.querySelector(selector);
const units = (course) => {
  const match = String(course.units ?? "").match(/(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?/);
  return match ? Number(match[2] || match[1]) : 0;
};
const courseKey = (course) => course.code;

async function init() {
  try {
    const manifestResponse = await fetch(`${API_BASE}/api/manifest`);
    if (!manifestResponse.ok) throw new Error(`API returned ${manifestResponse.status}`);
    const manifest = await manifestResponse.json();
    state.programs = manifest.programs.map(program => ({ ...program, available: true }));
    // The scraper owns program IDs. Do not rely on the old prototype ID
    // (`cpp-cs-bs`), which predates data/manifest.json.
    if (!state.programs.some(program => program.id === state.selectedProgram)) {
      state.selectedProgram = state.programs[0]?.id;
    }
    state.selectedPrograms = [state.selectedProgram];
    state.ge = await (await fetch(`${API_BASE}/api/general-education`)).json();
    await restoreAuth();
    await loadPlan();
    await loadProgramData(state.selectedPrograms);
    renderAll();
    if (CURRENT_PAGE === "login" && state.user) { showPage("terms"); return; }
    bindEvents();
    bindAuthEvents();
  } catch (error) {
    document.querySelector("main").innerHTML = `<div class="panel unavailable"><h2>Could not load planner data</h2><p>Start the FastAPI backend on <code>http://localhost:8000</code>, then reload this page.</p><code>${error.message}</code></div>`;
  }
}

async function loadProgramData(programIds) {
  const responses = await Promise.all(programIds.map(id => fetch(`${API_BASE}/api/programs/${encodeURIComponent(id)}`)));
  if (responses.some(response => !response.ok)) throw new Error("One or more program records could not be loaded");
  const programs = await Promise.all(responses.map(response => response.json()));
  const categories = {};
  const courseMap = new Map();
  state.programTotalUnits = 0;
  programs.forEach(program => {
    const escapedName = program.name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const statedUnits = program.program_text?.match(new RegExp(`${escapedName}\\s*:\\s*(\\d+)\\s+units`, "i"));
    state.programTotalUnits += statedUnits ? Number(statedUnits[1]) : 0;
    program.requirements.forEach(requirement => {
      const categoryName = `${program.name} — ${requirement.name}`;
      categories[categoryName] = requirement.courses.map(code => program.courses.find(course => course.code === code)).filter(Boolean);
      categories[categoryName].forEach(course => {
        if (!courseMap.has(course.code)) courseMap.set(course.code, { ...course, category: categoryName });
        else if (course.ge && !courseMap.get(course.code).ge) courseMap.get(course.code).ge = course.ge;
      });
    });
  });
  state.categories = categories;
  state.courses = [...courseMap.values()];
  state.geEnabled = programs.some(program => /,\s*B\.[AS]\.|Bachelor/i.test(program.name));
}

function defaultTerms() { return [{ id: crypto.randomUUID(), name: "Fall 2026", courses: [] }, { id: crypto.randomUUID(), name: "Spring 2027", courses: [] }, { id: crypto.randomUUID(), name: "Fall 2027", courses: [] }]; }
async function restoreAuth() {
  const response = await fetch(`${API_BASE}/api/auth/me`, { credentials: "include" });
  state.user = response.ok ? await response.json() : null;
}
async function loadPlan() {
  if (!state.user) { state.terms = defaultTerms(); return; }
  const response = await fetch(`${API_BASE}/api/me/plan`, { credentials: "include" });
  if (!response.ok) throw new Error("Could not load your plan");
  const data = await response.json();
  state.terms = data.terms?.length ? data.terms : defaultTerms();
  if (data.selected_programs?.length) state.selectedPrograms = data.selected_programs;
}
async function savePlan() { if (state.user) { const response = await fetch(`${API_BASE}/api/me/plan`, { method: "PUT", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ terms: state.terms, selected_programs: state.selectedPrograms }) }); if (!response.ok) { showToast("Could not save plan"); return; } } const saveStatus = $("#saveStatus"); if (saveStatus) { saveStatus.textContent = "Saved just now"; setTimeout(() => { saveStatus.textContent = ""; }, 1600); } }
function plannedCodes() { return new Set(state.terms.flatMap(term => term.courses)); }
function plannedCourses() { return state.courses.filter(course => plannedCodes().has(courseKey(course))); }
function totalPlannedUnits() { return plannedCourses().reduce((sum, course) => sum + units(course), 0); }
function geAreas(course) {
  const tags = String(course.ge || "").toUpperCase().match(/GE\s+([0-9]+[A-Z]?)/g) || [];
  return tags.map(tag => tag.replace(/^GE\s+/, "")).map(tag => (tag === "4C" || tag === "5D") ? "UD4" : tag);
}
function geCourses(requirementId) { return state.courses.filter(course => geAreas(course).includes(requirementId)); }
function geProgress() {
  if (!state.geEnabled || !state.ge) return { completed: 0, total: 0, remaining: 0 };
  const planned = plannedCodes();
  const completed = state.ge.requirements.reduce((sum, requirement) => {
    const taken = geCourses(requirement.id).filter(course => planned.has(course.code)).reduce((unitsTaken, course) => unitsTaken + units(course), 0);
    return sum + Math.min(taken, requirement.units);
  }, 0);
  return { completed, total: state.ge.total_units, remaining: Math.max(state.ge.total_units - completed, 0) };
}
function requirementUnits(name, courses) {
  const match = name.match(/:\s*(\d+(?:\.\d+)?)(?:-(\d+(?:\.\d+)?))?\s*units?/i);
  return match ? Number(match[2] || match[1]) : courses.reduce((sum, course) => sum + units(course), 0);
}
function showPage(page) {
  window.location.href = page === "terms" ? "/" : `/${page}`;
}
function renderAll() { if ($("#programSelect")) renderProgram(); if ($("#summaryGrid")) renderSummary(); if ($("#terms")) renderTerms(); if ($("#progressPercent")) renderProgress(); if ($("#recommendations")) renderRecommendations(); if ($("#courseGrid")) renderCatalog(); }

function renderProgram() {
  const select = $("#programSelect"); select.innerHTML = state.programs.map(p => `<option value="${p.id}" ${p.id === state.selectedProgram ? "selected" : ""}>${p.name}${p.available ? "" : " · data coming soon"}</option>`).join("");
  const current = state.programs.find(p => p.id === state.selectedProgram); $("#programMeta").innerHTML = `${current.department} · ${state.courses.length} program courses loaded<br><a href="${current.source_url}" target="_blank" rel="noreferrer">View official program page ↗</a>`;
}
function renderProgram() {
  const select = $("#programSelect");
  select.innerHTML = state.programs.map(p => `<option value="${p.id}" ${state.selectedPrograms.includes(p.id) ? "selected" : ""}>${p.name}</option>`).join("");
  const current = state.programs.filter(p => state.selectedPrograms.includes(p.id));
  const departments = [...new Set(current.map(p => p.department))].join(", ");
  $("#programMeta").innerHTML = `${current.length} program${current.length === 1 ? "" : "s"} selected · ${departments}<br>${state.courses.length} combined program courses loaded`;
}
function renderSummary() {
  const total = state.programTotalUnits || state.courses.reduce((sum, c) => sum + units(c), 0), planned = totalPlannedUnits(), remaining = Math.max(total - planned, 0), ge = geProgress();
  const stats = [[`${planned}`, "units planned"], [`${remaining}`, "degree units to map"], [`${state.terms.length}`, "terms on your roadmap"], [`${plannedCourses().length}`, "courses selected"]];
  if (state.geEnabled) stats.splice(2, 0, [`${ge.completed}/${ge.total}`, "GE units completed"]);
  $("#summaryGrid").innerHTML = stats.map(([value, label]) => `<div class="stat"><div class="stat-value">${value}</div><div class="stat-label">${label}</div></div>`).join("");
  $("#plannerNote").textContent = `${planned} units mapped across ${state.terms.length} terms. GE-tagged major courses count toward both views, but only once toward the degree total.`;
}
function renderTerms() {
  const container = $("#terms"); if (!state.terms.length) { container.innerHTML = `<div class="planner-empty">Your roadmap is empty. Add a term to begin.</div>`; return; }
  const moveOptions = (currentId) => state.terms.filter(term => term.id !== currentId).map(term => `<option value="${term.id}">${term.name}</option>`).join("");
  container.innerHTML = state.terms.map(term => { const termCourses = term.courses.map(code => state.courses.find(c => c.code === code)).filter(Boolean); const termUnits = termCourses.reduce((sum, c) => sum + units(c), 0); return `<article class="term"><div class="term-header"><div class="term-title"><strong>${term.name}</strong><span class="term-units">${termUnits} units</span></div><div class="term-actions"><button data-action="rename-term" data-id="${term.id}">Rename</button><button data-action="remove-term" data-id="${term.id}">Remove</button></div></div><div class="term-body" data-term="${term.id}">${termCourses.length ? termCourses.map(c => `<div class="planned-course" draggable="true" data-code="${c.code}" data-term="${term.id}"><span><strong>${c.code}</strong><span class="course-title">${c.title}</span></span><span><select class="move-course" aria-label="Move ${c.code} to another term" data-action="move-course" data-code="${c.code}" data-term="${term.id}"><option value="">Move to…</option>${moveOptions(term.id)}</select><button class="remove-course" title="Remove from term" data-action="remove-course" data-term="${term.id}" data-code="${c.code}">×</button></span></div>`).join("") : `<div class="empty-term">No courses yet. Drop a course here to move it into this term.</div>`}</div></article>`; }).join("");
}

function moveCourse(code, fromId, toId) {
  if (!toId || fromId === toId) return;
  const from = state.terms.find(term => term.id === fromId); const to = state.terms.find(term => term.id === toId);
  if (!from || !to || to.courses.includes(code)) return;
  from.courses = from.courses.filter(item => item !== code); to.courses.push(code); savePlan(); renderAll();
}
function renderProgress() {
  const total = state.programTotalUnits || state.courses.reduce((sum, c) => sum + units(c), 0), planned = totalPlannedUnits(), percent = total ? Math.min(Math.round(planned / total * 100), 100) : 0; $("#progressPercent").textContent = `${percent}%`; $("#progressBar").style.width = `${percent}%`; $("#progressCopy").textContent = `${planned} of ${total} program units currently mapped`;
  const major = Object.entries(state.categories).map(([name, list]) => { const categoryTotal = requirementUnits(name, list); const categoryPlanned = Math.min(list.filter(c => plannedCodes().has(c.code)).reduce((sum, c) => sum + units(c), 0), categoryTotal); const pct = categoryTotal ? Math.min(categoryPlanned / categoryTotal * 100, 100) : 0; return `<div class="requirement"><div class="requirement-row"><span>${name.replace(/:.*$/, "")}</span><span>${categoryPlanned}/${categoryTotal} units</span></div><div class="requirement-bar"><div style="width:${pct}%"></div></div></div>`; }).join("");
  const ge = state.geEnabled ? `<div class="requirement ge-heading"><div class="requirement-row"><strong>General education · ${geProgress().completed}/${state.ge.total_units} units</strong><a href="${state.ge.source_url}" target="_blank" rel="noreferrer">Catalog ↗</a></div></div>` + state.ge.requirements.map(requirement => { const list = geCourses(requirement.id); const completed = Math.min(list.filter(c => plannedCodes().has(c.code)).reduce((sum, c) => sum + units(c), 0), requirement.units); const pct = Math.min(completed / requirement.units * 100, 100); return `<div class="requirement"><div class="requirement-row"><span>${requirement.name}</span><span>${completed}/${requirement.units} units</span></div><div class="requirement-bar"><div style="width:${pct}%"></div></div></div>`; }).join("") : "";
  $("#requirementList").innerHTML = major + ge;
}
function renderRecommendations() { const candidates = state.courses.filter(c => !plannedCodes().has(c.code)).sort((a,b) => Number(a.code.match(/\d+/)?.[0] || 9999) - Number(b.code.match(/\d+/)?.[0] || 9999)).slice(0, 4); $("#recommendations").innerHTML = candidates.length ? candidates.map(c => `<div class="recommendation"><div><strong>${c.code}</strong><small>${c.title}</small></div><button class="button button-small" data-action="add-course" data-code="${c.code}">Add</button></div>`).join("") : `<div class="unavailable">Everything in this catalog is planned.</div>`; }
function renderCatalog() {
  const filter = $("#categoryFilter"); const categories = Object.keys(state.categories); filter.innerHTML = `<option value="all">All requirements</option>${categories.map(c => `<option value="${c}" ${c === state.category ? "selected" : ""}>${c}</option>`).join("")}`;
  const query = state.search.toLowerCase(); const results = state.courses.filter(c => (state.category === "all" || c.category === state.category) && `${c.code} ${c.title} ${c.description}`.toLowerCase().includes(query)); $("#courseCount").textContent = `${state.courses.length} courses loaded`;
  $("#courseGrid").innerHTML = results.length ? results.map(c => { const isPlanned = plannedCodes().has(c.code); const ge = c.ge ? `<span class="course-ge">${c.ge}</span>` : ""; return `<article class="course-card ${isPlanned ? "is-planned" : ""}"><div class="course-category">${c.category.replace(/:.*$/, "")}</div><div class="course-card-top"><span class="course-code">${c.code}</span><span class="course-units">${units(c)} units</span></div><h4>${c.title}</h4><p>${c.description || "No description available."}</p>${ge}${isPlanned ? `<button class="button button-small" disabled>Already planned</button>` : `<button class="button button-small" data-action="add-course" data-code="${c.code}">+ Add to next term</button>`}</article>`; }).join("") : `<div class="unavailable">No courses match your search.</div>`;
}

function addCourse(code, termId = state.terms[0]?.id) { if (!termId) return; if (plannedCodes().has(code)) { showToast("That course is already planned"); return; } const term = state.terms.find(t => t.id === termId); term.courses.push(code); savePlan(); renderAll(); showToast(`${code} added to ${term.name}`); }
function bindEvents() {
  document.querySelectorAll("[data-page-link]").forEach(link => link.addEventListener("click", event => { event.preventDefault(); showPage(link.dataset.pageLink); }));
  $("#loginPageButton")?.addEventListener("click", () => openAuth("login"));
  $("#programSelect")?.addEventListener("change", async e => { const selected = [...e.target.selectedOptions].map(option => option.value); if (!selected.length) return; state.selectedPrograms = selected; state.selectedProgram = selected[0]; await loadProgramData(selected); await savePlan(); renderAll(); });
  $("#courseSearch")?.addEventListener("input", e => { state.search = e.target.value; renderCatalog(); }); $("#categoryFilter")?.addEventListener("change", e => { state.category = e.target.value; renderCatalog(); });
  $("#addTerm")?.addEventListener("click", () => { const names = ["Fall", "Spring", "Summer", "Fall"]; const next = state.terms.length + 1; state.terms.push({ id: crypto.randomUUID(), name: `${names[next % names.length]} ${2026 + Math.floor(next / 2)}`, courses: [] }); savePlan(); renderAll(); });
  $("#resetPlan")?.addEventListener("click", () => { if (confirm("Clear every course from your roadmap?")) { state.terms = []; savePlan(); renderAll(); } });
  document.addEventListener("click", e => { const action = e.target.closest("[data-action]")?.dataset; if (!action) return; if (action.action === "add-course") addCourse(action.code); if (action.action === "remove-course") { const term = state.terms.find(t => t.id === action.term); term.courses = term.courses.filter(code => code !== action.code); savePlan(); renderAll(); } if (action.action === "remove-term") { state.terms = state.terms.filter(t => t.id !== action.id); savePlan(); renderAll(); } if (action.action === "rename-term") { const term = state.terms.find(t => t.id === action.id); const name = prompt("Term name", term.name); if (name?.trim()) { term.name = name.trim(); savePlan(); renderAll(); } } });
  document.addEventListener("change", e => { const action = e.target.closest("[data-action]")?.dataset; if (action?.action === "move-course") moveCourse(action.code, action.term, e.target.value); });
  document.addEventListener("dragstart", e => { const course = e.target.closest(".planned-course"); if (course) e.dataTransfer.setData("text/plain", JSON.stringify({ code: course.dataset.code, fromId: course.dataset.term })); });
  document.addEventListener("dragover", e => { if (e.target.closest(".term-body")) e.preventDefault(); });
  document.addEventListener("drop", e => { const body = e.target.closest(".term-body"); if (!body) return; e.preventDefault(); try { const data = JSON.parse(e.dataTransfer.getData("text/plain")); moveCourse(data.code, data.fromId, body.dataset.term); } catch (_) {} });
}
function openAuth(mode) { state.authMode = mode; $("#authOverlay").hidden = false; $("#authTitle").textContent = mode === "login" ? "Sign in" : "Create account"; $("#authSubtitle").textContent = mode === "login" ? "Save your roadmap across sessions." : "Create an account to keep your roadmap private."; $("#authSubmit").textContent = mode === "login" ? "Sign in" : "Create account"; $("#authSwitch").textContent = mode === "login" ? "Need an account? Register" : "Already have an account? Sign in"; $("#authError").textContent = ""; }
function bindAuthEvents() {
  $("#authButton")?.addEventListener("click", async () => { if (!state.user) return CURRENT_PAGE === "login" ? openAuth("login") : showPage("login"); await fetch(`${API_BASE}/api/auth/logout`, { method: "POST", credentials: "include" }); state.user = null; showPage("login"); });
  $("#authClose")?.addEventListener("click", () => { if (state.user) $("#authOverlay").hidden = true; });
  $("#authSwitch")?.addEventListener("click", () => openAuth(state.authMode === "login" ? "register" : "login"));
  $("#authForm")?.addEventListener("submit", async event => { event.preventDefault(); const email = $("#authEmail").value; const password = $("#authPassword").value; $("#authError").textContent = ""; try { const response = await fetch(`${API_BASE}/api/auth/${state.authMode}`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) }); const result = await response.json(); if (!response.ok) throw new Error(result.detail || result.message || "Authentication failed"); if (!result.user) { $("#authError").textContent = result.message; return; } state.user = result.user; $("#authOverlay").hidden = true; await loadPlan(); showPage("terms"); } catch (error) { $("#authError").textContent = error.message; } });
  if ($("#authButton") && CURRENT_PAGE !== "login") $("#authButton").textContent = state.user ? "Log out" : "Log in";
}
function showToast(message) { const toast = $("#toast"); toast.textContent = message; toast.classList.add("show"); setTimeout(() => toast.classList.remove("show"), 1800); }
init();
