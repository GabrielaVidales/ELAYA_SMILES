console.log(">>> app.js está cargado");

/// Configuración global
const API_BASE_URL = window.location.origin + '/api';
let molecules = [];
let selected = new Set();
let currentVisualizations = [];
let currentXYZ = '';
let currentMoleculeIndex = 0;
let rotationSpeed = 0.8;
let isRotationPaused = false;
let rotationAnimationId = null;
let selectedMolecules = new Set();
let visualizationContainer, viewerContainer, moleculeTitle, moleculeControls;
let prevMoleculeBtn, nextMoleculeBtn, rotationSpeedInput;
let showConfirmation = true;
let allMolecules = [];
const legacyDownloadBtn = document.getElementById('download-xyz');

// === BRIDGE: sincroniza let-globales con window.* ===
Object.defineProperty(window, 'molecules', {
  get: () => molecules,
  set: (v) => { molecules = Array.isArray(v) ? v : []; }
});
Object.defineProperty(window, 'currentMoleculeIndex', {
  get: () => currentMoleculeIndex,
  set: (v) => { currentMoleculeIndex = Number.isInteger(v) ? v : 0; }
});
Object.defineProperty(window, 'currentXYZ', {
  get: () => currentXYZ,
  set: (v) => { currentXYZ = (v ?? '').toString(); }
});
Object.defineProperty(window, 'allMolecules', {
  get: () => allMolecules,
  set: (v) => { allMolecules = Array.isArray(v) ? v : []; }
});

console.log("DOM fully loaded and parsed");

document.addEventListener("DOMContentLoaded", function () {
    console.log("✅ DOM fully loaded and parsed");

    // === Cache UI elements early ===
    visualizationContainer = document.querySelector('.visualization-container');
    viewerContainer        = document.getElementById('viewer-container');
    moleculeTitle          = document.getElementById('molecule-title');
    moleculeControls       = document.getElementById('molecule-controls');
    prevMoleculeBtn        = document.getElementById('prev-molecule');
    nextMoleculeBtn        = document.getElementById('next-molecule');
    rotationSpeedInput     = document.getElementById('rotation-speed');

    // Hook prev/next once
    if (prevMoleculeBtn) prevMoleculeBtn.addEventListener('click', () => navigateMolecules(-1));
    if (nextMoleculeBtn) nextMoleculeBtn.addEventListener('click', () => navigateMolecules(1));

    // Setup slider once
    if (rotationSpeedInput) {
    rotationSpeedInput.min   = 0;
    rotationSpeedInput.max   = 5;
    rotationSpeedInput.step  = 0.5;
    rotationSpeedInput.value = String(rotationSpeed);
    rotationSpeedInput.addEventListener('input', (e) => changeRotationSpeed(e.target.value));
    }

    // Inicializar modo de entrada
    try {
        toggleInputMethod();
    } catch (e) {
        console.warn("⚠️ Error en toggleInputMethod:", e);
    }

    // Inicializar opciones de campo de fuerza (el DOM puede no estar listo aún, se reintenta en el change handler)
    try {
        toggleForceField();
    } catch (e) {
        // Silenciado: se vuelve a llamar cuando el usuario cambia el método de conversión
    }

    // v2.4.2: no molecule is preloaded any more. A ready-made result on the first visit skipped the
    // steps the page now teaches (enter → settings → convert) and cost a cold-start conversion on the
    // server; oxytocin is offered as an example chip instead.

    // Conexión al backend
    try {
        checkBackendConnection();
    } catch (e) {
        console.warn("⚠️ Error en checkBackendConnection:", e);
    }

    // Historial
    try {
        loadSmilesHistory();
    } catch (e) {
        console.warn("⚠️ Error cargando historial:", e);
    }

        const smilesInputEl = document.getElementById('smiles');
    if (smilesInputEl) {
      smilesInputEl.addEventListener('input', () => {
        // Al teclear un SMILES, asumimos modo single y “olvidamos” el archivo previo
        window.allMolecules = [];
        const singleRadio = document.querySelector('input[name="input-method"][value="single"]');
        if (singleRadio) singleRadio.checked = true;
        toggleInputMethod?.();
        updateNavigationButtons?.();
        updateDownloadButtons();
      });
    }

    // ── Helper: set active nav tab ───────────────────────────
    function setActiveNav(id) {
        document.querySelectorAll('.navbar a').forEach(a => a.classList.remove('nav-active'));
        const el = document.getElementById(id);
        if (el) el.classList.add('nav-active');
    }

    // ── Scroll-triggered animations (fade-in + scroll-reveal) ──
    const fadeObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                entry.target.classList.add('sr-visible');
                fadeObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.07 });

    function observeFadeIns() {
        document.querySelectorAll('.fade-in-section, .scroll-reveal').forEach(el => {
            // Only reset elements inside hidden sections to avoid flashing
            // content that is already visible on screen.
            const parentSection = el.closest('section, [id$="-section"]');
            const isInVisibleSection = parentSection
                ? window.getComputedStyle(parentSection).display !== 'none'
                : true;
            if (!isInVisibleSection) {
                el.classList.remove('visible', 'sr-visible');
            }
            fadeObserver.observe(el);
        });
    }
    observeFadeIns();

    // Navegación: About
    const aboutLink = document.querySelector('a[href="#about"]');
    const aboutSection = document.getElementById('about-section');
    const inputSection = document.querySelector('.input-section');
    const conversionSection = document.querySelector('.conversion-section');
    const header = document.querySelector('header');
    const viewer = document.getElementById('viewer-container');
    const conversionMethod = document.getElementById('conversion-method');

    if (conversionMethod) {
        conversionMethod.addEventListener('change', toggleForceField);
    } else {
        console.warn("⚠️ conversion-method no encontrado");
    }

    if (aboutLink) {
        aboutLink.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelectorAll('main > section').forEach(section => section.style.display = 'none');
            if (aboutSection) {
                aboutSection.style.display = 'block';
                setTimeout(() => {
                    window.scrollTo({ top: aboutSection.offsetTop - 40, behavior: 'smooth' });
                    observeFadeIns();
                }, 100);
            }
            if (header) header.style.display = 'none';
            setActiveNav('nav-about');
        });
    }

    const postOptSelect = document.getElementById("post-optimization");
    const glomosPanel = document.getElementById("glomos-panel");

    postOptSelect.addEventListener("change", () => {
      glomosPanel.style.display =
        postOptSelect.value === "glomos" ? "block" : "none";
    });

    // Navegación: Explore
    const simulatorLink = document.querySelector('a[href="#explore"]');
    if (simulatorLink) {
        simulatorLink.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelectorAll('main > section').forEach(section => section.style.display = 'none');
            if (inputSection) inputSection.style.display = 'block';
            if (conversionSection) conversionSection.style.display = 'flex';
            if (header) header.style.display = 'block';
            window.scrollTo({ top: 0, behavior: 'smooth' });
            setActiveNav('nav-explore');
            setTimeout(() => { observeFadeIns(); }, 100);
        });
    }

    // Navegación: Contact
    const contactLink = document.querySelector('a[href="#contact"]');
    const contactSection = document.getElementById('contact-section');

    if (contactLink) {
        contactLink.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelectorAll('main > section').forEach(section => section.style.display = 'none');
            if (contactSection) {
                contactSection.style.display = 'block';
                setTimeout(() => {
                    window.scrollTo({ top: contactSection.offsetTop - 40, behavior: 'smooth' });
                    observeFadeIns();
                }, 100);
            }
            if (header) header.style.display = 'none';
            setActiveNav('nav-contact');
        });
    }

    // Default: Explore is the landing tab
    setActiveNav('nav-explore');

    const btnConvert = document.getElementById('convert-molecules');
    if (btnConvert) {
    btnConvert.addEventListener('click', async (e) => {
        // 1) Evita submit/refresh si está dentro de un <form>
        e.preventDefault();
        e.stopPropagation();

        // 2) Normaliza el método seleccionado (evita espacios y mayúsculas)
        const selectedEl = document.querySelector('input[name="input-method"]:checked');
        let selectedMethod = selectedEl?.value;
        selectedMethod = selectedMethod?.trim().toLowerCase(); // <-- clave

        try {
        if (selectedMethod === 'single') {
            const smilesInput = document.getElementById('smiles');
            const smiles = smilesInput?.value?.trim();

            if (!smiles) {
            showError("Please enter a valid SMILES string.");
            return;
            }

            // Loader / bloqueo
            const convertBtn = document.getElementById('convert-molecules');
            const loader = convertBtn?.querySelector('.water-loader');
            const label  = convertBtn?.querySelector('.button-label');
            if (loader && label) {
            loader.style.display = 'block';
            label.style.opacity  = '0.3';
            convertBtn.disabled  = true;
            if (typeof createBubbles === 'function') createBubbles(loader);
            }

            // Estado y conversión
            window.molecules = [{ smiles, id: smiles }];
            window.currentMoleculeIndex = 0;
            if (typeof updateSmilesHistory === 'function') updateSmilesHistory(smiles);

            // Siempre quitar el panel GLOMOS si no se usa GLOMOS
            const postOpt = document.getElementById('post-optimization')?.value;
            if (postOpt !== 'glomos') {
              document.getElementById('glomos-live-panel')?.remove();
            }

            // ── GLOMOS (background job with live progress) ───────────
            if (postOpt === 'glomos' && typeof window.runGlomosWithStream === 'function') {
              currentXYZ = '';
              const viewerEl = document.getElementById('viewer-container');
              if (viewerEl) {
                viewerEl.innerHTML = '<div class="placeholder" style="display:flex;align-items:center;justify-content:center;height:100%;color:#3cb49a;font-size:0.9rem;">⟳ GLOMOS running…</div>';
              }
              const xyzDisplayEl = document.getElementById('xyz-display');
              if (xyzDisplayEl) { xyzDisplayEl.textContent = ''; xyzDisplayEl.style.display = 'none'; }
              updateDownloadButtons?.();

              const unlock = () => {
                if (loader && label) {
                  loader.style.display = 'none';
                  label.style.opacity  = '1';
                  convertBtn.disabled  = false;
                  loader.innerHTML     = '';
                }
              };
              window.runGlomosWithStream(
                smiles,
                collectGlomosParams(),
                (xyzResult, result) => {
                  unlock();
                  window.glomosResult = result;
                  showGlomosConformer(result?.conformers?.[0] || { xyz: xyzResult }, smiles);
                  const n = result?.conformers?.length ?? 1;
                  const partial = result?.partial ? ' (partial result)' : '';
                  showSuccess?.(`<strong>✔ GLOMOS finished${partial}</strong><br>${n} conformer(s) found; the lowest-energy one is shown.`);
                },
                (errMsg) => {
                  unlock();
                  showError?.('GLOMOS: ' + errMsg);
                },
                (conf) => showGlomosConformer(conf, smiles)
              );
              return;
            }
            // ─────────────────────────────────────────────────────────

            await convertSingleMolecule();

            // Reset UI
            if (loader && label) {
            loader.style.display = 'none';
            label.style.opacity  = '1';
            convertBtn.disabled  = false;
            loader.innerHTML = '';
            }
            if (typeof updateNavigationButtons === 'function') updateNavigationButtons();
            return;

        } else if (selectedMethod === 'file') {
            // Asegura que exista allMolecules
            if (!Array.isArray(window.allMolecules) || window.allMolecules.length === 0) {
            showError("No molecules loaded from file.");
            return;
            }

            // Selection made in the file table (ElayaFileSel); the modal is only a fallback
            let picked = window.ElayaFileSel ? window.ElayaFileSel.picked() : null;
            if (!picked) {
                document.getElementById('molecule-selection-modal')?.remove();
                const selectedSet = await showMoleculeSelectionModal(window.allMolecules);
                if (selectedSet && selectedSet.size) {
                    const pickedIdx = [...selectedSet].map(Number).filter(i => i >= 0 && i < window.allMolecules.length).sort((a,b)=>a-b);
                    picked = pickedIdx.map(i => window.allMolecules[i]);
                }
            }
            if (picked && picked.length) await window.elayaConvertPicked(picked);
            else showError("No molecules selected: tick at least one in the table.");

        } else {
            showError("Please select an input method.");
        }
        } catch (error) {
        console.error(error);
        showError(error?.message || "Conversion failed.");
        }
    });
    }

    // Convert a list of molecules from a file (table buttons "Convert all / selected" and the Convert button)
    window.elayaConvertPicked = async function (picked) {
        window.molecules = picked;
        window.currentMoleculeIndex = 0;
        const smilesInput = document.getElementById('smiles');
        if (smilesInput) smilesInput.value = '';
        const postOptFile = document.getElementById('post-optimization')?.value;
        if (postOptFile !== 'glomos') document.getElementById('glomos-live-panel')?.remove();
        try {
            await convertMolecules(picked);
            if (postOptFile === 'glomos') await runGlomosBatch(picked);
            document.querySelector('.visualization-container')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        } catch (e) {
            showError(e?.message || 'Conversion failed.');
        }
    };

    // === FILE CHANGE HANDLER (ajuste) ===
    const smilesFileEl = document.getElementById('smiles-file');
    if (smilesFileEl) {
    smilesFileEl.addEventListener('change', async function () {
        try {
        const file = this.files?.[0];
        if (!file) throw new Error("No file selected");

        // Marca 'file' y actualiza UI del método
        const fileRadio = document.querySelector('input[name="input-method"][value="file"]');
        if (fileRadio) {
            fileRadio.checked = true;
            toggleInputMethod?.();
        }

        const fileSpan = document.getElementById('file-selected');
        if (fileSpan) fileSpan.textContent = file.name;

        const text = await file.text();

        // .smi / .txt (SMILES [name]) and .csv / .tsv (smiles column) — see ux_extras.js
        const parsed = window.ElayaFiles ? window.ElayaFiles.parse(text, file.name) : (() => {
            const out = [];
            text.split('\n').forEach((line) => {
                const trimmed = line.trim();
                if (!trimmed || /^#|^\/\//.test(trimmed)) return;
                const parts = trimmed.split(/\s+/);
                out.push({ smiles: parts[0], id: (parts[1] || `mol_${out.length + 1}`) });
            });
            return out;
        })();

        if (parsed.length === 0) throw new Error("No SMILES found in the file (see the format help below)");

        // Reset de estado global
        window.allMolecules = parsed.slice();
        window.molecules    = parsed.slice();
        window.currentMoleculeIndex = 0;
        window.selected?.clear?.();

        window.dispatchEvent(new CustomEvent('elaya:file-loaded', { detail: { name: file.name, molecules: parsed } }));

        const loadConfirmation = document.getElementById('load-confirmation');
        if (false && loadConfirmation && window.showConfirmation) {
            const moleculeInfo = window.molecules
            .map(mol => `<div><strong>SMILES:</strong> ${mol.smiles}</div>`)
            .join('<hr>');
            loadConfirmation.innerHTML = `
            <div class="alert success">
                <strong>${window.molecules.length} molécula(s) cargadas:</strong><br>
                ${moleculeInfo}
            </div>`;
            loadConfirmation.style.display = 'block';
            setTimeout(() => (loadConfirmation.style.display = 'none'), 2000);
        }

        const convertBtn = document.getElementById('convert-molecules');
        if (convertBtn) convertBtn.disabled = false;

        } catch (error) {
        console.error("❌ Error al cargar archivo:", error);
        showError(`Could not read the file: ${error.message}`);
        }
    });
    }
});

document.querySelectorAll('#smiles-examples [data-smiles]').forEach(chip => {
    chip.addEventListener('click', () => {
        const smiles = chip.getAttribute('data-smiles');
        const smilesInput = document.getElementById('smiles');
        if (smilesInput) {
            smilesInput.value = smiles;
            smilesInput.classList.add('touched');
            smilesInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
        document.querySelectorAll('#smiles-examples .example-chip').forEach(c => c.classList.toggle('active', c === chip));
    });
});

// v2.4.3: Enter no longer converts (it surprised new users); the Convert button is the one way to run.
(function () {
    const smilesInput = document.getElementById('smiles');
    if (!smilesInput) return;
    // typing by hand clears the highlighted example
    smilesInput.addEventListener('input', (e) => {
        if (!e.isTrusted) return;
        document.querySelectorAll('#smiles-examples .example-chip.active').forEach(c => c.classList.remove('active'));
    });
})();

    // Event listeners
document.querySelectorAll('input[name="input-method"]').forEach(radio => {
    radio.addEventListener('change', (e) => {
        // Cambia la vista del input según la opción seleccionada
        toggleInputMethod();

        // Si se selecciona "single", limpia cualquier molécula previa
        if (e.target.value === 'single') {
            window.allMolecules = [];  // limpia las moléculas cargadas desde archivo
            window.currentMoleculeIndex = 0;  // reinicia el índice
            updateNavigationButtons?.();      // actualiza botones next/before
            updateDownloadButtons();
        }
    });
});

const btnLoadSmiles = document.getElementById('load-smiles');
if (btnLoadSmiles) btnLoadSmiles.addEventListener('click', loadSmiles);

const btnDownloadXYZ = document.getElementById('download-xyz');
if (btnDownloadXYZ) {
  btnDownloadXYZ.addEventListener('click', () => {
    if (molecules && molecules.length > 1) {
      downloadAllXYZ();
    } else {
      downloadXYZ(); // tu función actual para el "currentXYZ"
    }
  });
}

const btnDownloadImage = document.getElementById('download-image');
if (btnDownloadImage) btnDownloadImage.addEventListener('click', downloadImage);

const btnDownloadFloating = document.getElementById('download-xyz-floating');
if (btnDownloadFloating) {
    btnDownloadFloating.addEventListener('click', () => {
        // structure on screen, in the format selected in the structure card
        if (window.ElayaPanel) window.ElayaPanel.downloadCurrent(); else downloadXYZ();
    });
}

document.querySelectorAll('.tab-btn').forEach(button => {
  button.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    button.classList.add('active');

    const format = button.getAttribute('data-format');
    document.querySelectorAll('.format-display').forEach(div => div.style.display = 'none');
    const displayDiv = document.getElementById(`${format}-display`);
    if (displayDiv) {
        displayDiv.style.display = 'block';
    } else {
        console.warn(`⚠ No se encontró el contenedor para el formato: ${format}-display`);
    }
  });
});

    // Inicializar 3Dmol después de que se cargue la librería
init3DMol();

document.querySelectorAll('input, select').forEach(el => {
    const type = el.getAttribute('type');
    
    // Para select y file usamos 'change', para text también usamos 'input'
    const eventType = (el.tagName === 'SELECT' || type === 'file') ? 'change' : 'input';
    
    el.addEventListener(eventType, () => {
        el.classList.add('touched');
    });
});

loadSmilesHistory();



// Efecto de rayo dorado al hacer clic en el título
const goldFlashLink = document.querySelector('.gold-flash');
const modal = document.createElement('div');
modal.className = 'modal-overlay';

if (goldFlashLink) {
    goldFlashLink.addEventListener('click', function (e) {
    e.preventDefault();
    this.classList.remove('clicked'); // reinicia si estaba activo
    void this.offsetWidth; // fuerza reflow para reiniciar animación
    this.classList.add('clicked');

    // quitar clase después de que termine la animación (~1s)
    setTimeout(() => {
            this.classList.remove('clicked');
        }, 1000); // debe coincidir con la duración del @keyframes
    });
}

console.log("Conexión con backend establecida");

let is3DEnabled = true;
let is2DEnabled = false;

// === Funciones de grabación y captura de imagen ===
const recordBtn = document.getElementById('record-btn');
const screenshotBtn = document.getElementById('screenshot-btn');
const countdownEl = document.getElementById('countdown');

let mediaRecorder;
let recordedChunks = [];
let isRecording = false;

if (recordBtn && screenshotBtn) {
    recordBtn.addEventListener('click', () => {
        if (!isRecording) {
            // Mostrar cuenta regresiva y luego iniciar grabación
            countdown(3, () => {
                startRecording();
                toggleRecordingUI(true);
                isRecording = true;
            });
        } else {
            stopRecording();
            toggleRecordingUI(false);
            isRecording = false;
        }
    });

    screenshotBtn.addEventListener('click', downloadImage);
}

// ── GLOMOS helpers ──────────────────────────────────────────────────────────
function collectGlomosParams() {
  const num = (id, d) => { const v = Number(document.getElementById(id)?.value); return Number.isFinite(v) ? v : d; };
  return {
    preset:            document.getElementById('glomos-preset')?.value || 'custom',
    initpop:           num('glomos-initpop', 6),
    matings:           num('glomos-matings', 4),
    mutants:           num('glomos-mutants', 4),
    generations:       num('glomos-generations', 4),
    energy_cutoff:     num('glomos-ecut', 6),
    cutoff_population: num('glomos-keep', 6),
    ani_model:         document.getElementById('glomos-ani')?.value || 'auto',
    max_minutes:       num('glomos-minutes', 10),
    random_seed:       num('glomos-seed', 0),
    screening:         document.getElementById('glomos-screening')?.value || 'ensemble',
  };
}

const GLOMOS_PRESETS = {
  fast:     { initpop: 6,  matings: 4,  mutants: 4,  generations: 4,  ecut: 6,  keep: 6 },
  standard: { initpop: 12, matings: 8,  mutants: 8,  generations: 8,  ecut: 8,  keep: 10 },
  thorough: { initpop: 30, matings: 16, mutants: 16, generations: 20, ecut: 10, keep: 20 },
};

document.addEventListener('DOMContentLoaded', () => {
  const sel = document.getElementById('glomos-preset');
  if (!sel) return;
  const map = { initpop: 'glomos-initpop', matings: 'glomos-matings', mutants: 'glomos-mutants',
                generations: 'glomos-generations', ecut: 'glomos-ecut', keep: 'glomos-keep' };
  sel.addEventListener('change', () => {
    const p = GLOMOS_PRESETS[sel.value];
    if (!p) return;
    Object.entries(map).forEach(([k, id]) => { const el = document.getElementById(id); if (el) el.value = p[k]; });
  });
  // editing any number switches the preset to "custom"
  Object.values(map).forEach(id => document.getElementById(id)?.addEventListener('input', () => { sel.value = 'custom'; }));
});

// Show one GLOMOS conformer (xyz text) in the main viewer
function showGlomosConformer(conf, smiles) {
  if (!conf || !conf.xyz) return;
  const idx = (typeof currentMoleculeIndex === 'number') ? currentMoleculeIndex : 0;
  const sm = smiles || molecules?.[idx]?.smiles || '';
  currentXYZ = conf.xyz;
  if (!Array.isArray(molecules) || !molecules[idx]) molecules = [{ smiles: sm, id: sm }];
  molecules[idx] = { ...molecules[idx], xyz: conf.xyz, molBlock: conf.mol || null };
  updateXYZDisplay?.();
  updateViewerContainerLayout();
  updateDownloadButtons?.();
  updateNavigationButtons?.();
}

// Run GLOMOS sequentially for every molecule loaded from a file
async function runGlomosBatch(picked) {
  const params = collectGlomosParams();
  const ok = [], failed = [];
  for (let i = 0; i < picked.length; i++) {
    const m = picked[i];
    const outcome = await new Promise(resolve => {
      window.runGlomosWithStream(m.smiles, params,
        (xyz, result) => resolve({ xyz, result }),
        (msg) => resolve({ error: msg }),
        (conf) => { if (i === currentMoleculeIndex) showGlomosConformer(conf, m.smiles); });
    });
    if (outcome.error) { failed.push(`${m.id || m.smiles}: ${outcome.error}`); continue; }
    ok.push(m.id || m.smiles);
    if (molecules[i]) molecules[i] = { ...molecules[i], xyz: outcome.xyz, molBlock: outcome.result?.conformers?.[0]?.mol || null, glomos: outcome.result };
  }
  currentMoleculeIndex = 0;
  if (molecules[0]) showGlomosConformer({ xyz: molecules[0].xyz, mol: molecules[0].molBlock }, molecules[0].smiles);
  if (failed.length) showError?.('GLOMOS failed for:<br>' + failed.join('<br>'));
  else showSuccess?.(`<strong>✔ GLOMOS finished for ${ok.length} molecule(s)</strong>`);
}

function extractXYZString(payload) {
  if (!payload) return '';
  // casos comunes
  if (typeof payload === 'string') return payload.trim();
  if (typeof payload.xyz === 'string') return payload.xyz.trim();
  if (payload.xyz && typeof payload.xyz.xyz === 'string') return payload.xyz.xyz.trim();
  if (typeof payload.XYZ === 'string') return payload.XYZ.trim();
  if (typeof payload.xyz_text === 'string') return payload.xyz_text.trim();
  if (payload.data && typeof payload.data === 'string') return payload.data.trim();
  // última opción: intenta JSON.stringify si viene objeto con campos sueltos
  try {
    const s = JSON.stringify(payload);
    return s || '';
  } catch { return ''; }
}

function selectFormatTab(fmt) {
  // activa la pestaña y el panel correspondientes si existen
  const tabs = document.querySelectorAll('[data-format-tab]');
  const panels = document.querySelectorAll('[data-format-panel]');
  tabs.forEach(t => t.classList.toggle('active', t.dataset.formatTab === fmt));
  panels.forEach(p => p.style.display = (p.dataset.formatPanel === fmt ? 'block' : 'none'));
}

function toggleRecordingUI(recording) {
    const svg = recordBtn.querySelector('svg');
    svg.innerHTML = recording
        ? `<rect x="8" y="8" width="8" height="8" />`
        : `<circle cx="12" cy="12" r="8" />`;

    recordBtn.classList.toggle('recording-blink', recording);
    recordBtn.title = recording ? "Click to stop and download the video" : "Record a video (WebM) of the rotating molecule";
    if (!recording) recLabel('Record');
}

// v2.4.3: the 3-2-1 countdown and the recording time are shown inside the Record button itself
function recLabel(text) {
    const lbl = recordBtn && recordBtn.querySelector('.tool-label');
    if (lbl) lbl.textContent = text;
}
function countdown(seconds, callback) {
    let current = seconds;
    recordBtn.classList.add('counting');
    recordBtn.disabled = true;
    recLabel(`${current}…`);
    const timer = setInterval(() => {
        current--;
        if (current > 0) { recLabel(`${current}…`); return; }
        clearInterval(timer);
        recordBtn.classList.remove('counting');
        recordBtn.disabled = false;
        callback();
    }, 1000);
}

let timerInterval;
let startTime;

let _liveCapture = null;
async function startRecording() {
    let canvas = document.querySelector('#viewer-container canvas');
    // v2.4.8: with 2D on, record the whole viewer (2D, or 3D + 2D side by side)
    if (is2DEnabled && window.ElayaView2D && document.querySelector('#viewer-2d svg')) {
        _liveCapture = await window.ElayaView2D.liveCanvas();
        canvas = _liveCapture.canvas;
    }
    if (!canvas) {
        console.error("⚠ No se encontró canvas para capturar.");
        return;
    }
    const stream = canvas.captureStream(30);
    console.log("Stream capturado desde canvas:", stream);
    
    mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });

    mediaRecorder.ondataavailable = function (e) {
        if (e.data.size > 0) {
            recordedChunks.push(e.data);
        }
    };

    mediaRecorder.onstop = function () {
        clearInterval(timerInterval);
        if (_liveCapture) { _liveCapture.stop(); _liveCapture = null; }
        recLabel('Record');

        const blob = new Blob(recordedChunks, { type: 'video/webm' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');

        const smilesId = window.molecules?.[window.currentMoleculeIndex]?.smiles?.replace(/[^a-zA-Z0-9]/g, "_") || `video_${Date.now()}`;
        const filename = `molecule_video_${smilesId}.webm`;

        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        URL.revokeObjectURL(url);
        recordedChunks = [];
    };

    mediaRecorder.start();
    startTimer();
}

function startTimer() {
    startTime = Date.now();
    recLabel('00:00');
    timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        recLabel(formatTime(elapsed));
    }, 1000);
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
}


function stopRecording() {
    clearInterval(timerInterval);
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
    }
}

function safeFileName(name) {
  return (name || 'unknown').replace(/[\\/:*?"<>|]/g, '_');
}

document.querySelectorAll('.info-icon').forEach(icon => {
    let timer;
    const tooltipId = icon.getAttribute('data-tooltip-id');
    const tooltip = document.getElementById(tooltipId);
    const url = icon.getAttribute('data-url');

    // Manejar hover para tooltip
    icon.addEventListener('mouseenter', () => {
        timer = setTimeout(() => {
            if (tooltip) tooltip.classList.add('visible');
        }, 300);
    });

    icon.addEventListener('mouseleave', () => {
        clearTimeout(timer);
        if (tooltip) tooltip.classList.remove('visible');
    });

    // Manejar click para abrir URL
    icon.addEventListener('click', (e) => {
        e.stopPropagation(); // Evitar que el evento se propague
        if (url) window.open(url, '_blank');
    });
});

document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => {
        const format = btn.dataset.format;
        fetch(`/files/mol_ejemplo.${format}`)
          .then(res => res.text())
          .then(data => {
              document.getElementById("text-preview").textContent = data;
          });
    });
});

const btn3D = document.getElementById("toggle-3d");
const btn2D = document.getElementById("toggle-2d");
    
btn3D.addEventListener("click", () => toggleView("3d"));
btn2D.addEventListener("click", () => toggleView("2d"));

// v2.4.11: 3D and 2D are independent switches again (both on = side by side, both off = nothing shown)
function syncViewButtons() {
  [[btn3D, is3DEnabled], [btn2D, is2DEnabled]].forEach(([b, on]) => {
    if (!b) return;
    b.classList.toggle("active", on);
    b.setAttribute("aria-pressed", on ? "true" : "false");
  });
}

function toggleView(mode) {
  if (mode === "3d") is3DEnabled = !is3DEnabled;
  else if (mode === "2d") is2DEnabled = !is2DEnabled;
  syncViewButtons();

  // Toggle mode-2d class for contrast styling (pure 2D = white bg)
  const visContainer = document.querySelector('.visualization-container');
  if (visContainer) {
    if (is2DEnabled && !is3DEnabled) visContainer.classList.add('mode-2d');
    else visContainer.classList.remove('mode-2d');
    visContainer.classList.toggle('mode-both', is2DEnabled && is3DEnabled);
  }

  updateViewerContainerLayout();
}

function updateViewerContainerLayout() {
  const viewer = document.getElementById('viewer-container') || document.querySelector('.visualization-container');
  const speedControl = document.querySelector(".speed-control");
  const mol = molecules[currentMoleculeIndex];

  if (!viewer) {
    console.warn("No viewer container found");
    return;
  }

  // 🔧 Forzamos que el root ocupe el área y use flex
  viewer.innerHTML = '';
  viewer.style.display = 'flex';
  viewer.style.flexDirection = 'row';
  viewer.style.alignItems = 'stretch';
  viewer.style.justifyContent = 'stretch';
  viewer.style.width = '100%';
  viewer.style.height = '100%';
  viewer.style.gap = '0';
  viewer.style.position = 'relative';

  if (!mol) {
    if (moleculeControls) moleculeControls.style.display = 'flex';
    if (speedControl) speedControl.style.display = (is3DEnabled) ? 'flex' : 'none';
    updateNavigationButtons?.();
    return;
  }

    // 🧪 Caso: 3D + 2D (mitad/mitad con 3D a la izquierda, 2D a la derecha)
  if (is3DEnabled && is2DEnabled) {
    const viewer3D = document.createElement('div');
    viewer3D.id = 'viewer-3d';
    viewer3D.style.flex = '1 1 50%';
    viewer3D.style.minWidth = '0';
    viewer3D.style.height = '100%';
    viewer3D.style.position = 'relative';

    const viewer2D = document.createElement('div');
    viewer2D.id = 'viewer-2d';
    viewer2D.style.flex = '1 1 50%';
    viewer2D.style.minWidth = '0';
    viewer2D.style.height = '100%';
    viewer2D.style.position = 'relative';
    viewer2D.style.display = 'flex';
    viewer2D.style.alignItems = 'center';       // centra verticalmente
    viewer2D.style.justifyContent = 'center';   // centra horizontalmente
    viewer2D.style.overflow = 'hidden';
    viewer2D.style.background = '#ffffff';      // fondo blanco para 2D
    viewer2D.style.borderLeft = '1px solid rgba(255,255,255,.12)';

    viewer.appendChild(viewer3D);
    viewer.appendChild(viewer2D);

    // 🔹 3D a la izquierda (igual que antes)
    const format = mol.molBlock ? 'sdf' : 'xyz';
    const modelData = mol.molBlock || mol.xyz;
    render3DMolecule(modelData, mol.smiles, format, viewer3D);

    // 🔹 2D a la derecha usando tu endpoint SVG (en lugar de Kekule)
    fetch('/api/draw2d', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ smiles: mol.smiles })
    })
    .then(r => { if (!r.ok) throw new Error('Error al obtener imagen 2D'); return r.text(); })
    .then(svg => {
        viewer2D.innerHTML = svg;
        const svgEl = viewer2D.querySelector('svg');
        if (svgEl) {
            // que llene su panel, centrado y sin deformar
            svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet');
            svgEl.style.display   = 'block';
            svgEl.style.width     = '100%';
            svgEl.style.height    = '100%';
            svgEl.style.maxWidth  = '95%';
            svgEl.style.maxHeight = '95%';
            }
    })
    .catch(err => {
        console.error("Error cargando visualización 2D:", err);
        viewer2D.textContent = "Error al mostrar estructura 2D.";
    });

    if (speedControl) speedControl.style.display = 'flex';
        return; // evita que siga evaluando otros casos
    }

  // 🧪 Solo 3D (ocupa todo)
  else if (is3DEnabled) {
    const viewer3D = document.createElement('div');
    viewer3D.id = 'viewer-3d';
    viewer3D.style.flex = '1 1 100%';
    viewer3D.style.minWidth = '0';
    viewer3D.style.height = '100%';
    viewer3D.style.position = 'relative';
    viewer.appendChild(viewer3D);

    const format = mol.molBlock ? 'sdf' : 'xyz';
    const modelData = mol.molBlock || mol.xyz;
    render3DMolecule(modelData, mol.smiles, format, viewer3D);

    if (speedControl) speedControl.style.display = 'flex';
  }

  // 🧪 Solo 2D (ocupa todo)
  else if (is2DEnabled) {
    const viewer2D = document.createElement('div');
    viewer2D.id = 'viewer-2d';
    viewer2D.style.flex = '0 0 100%';
    viewer2D.style.minWidth = '0';
    viewer2D.style.height = '180%';
    viewer2D.style.display = 'flex';
    viewer2D.style.alignItems = 'center';      // centra verticalmente
    viewer2D.style.justifyContent = 'center';  // centra horizontalmente
    viewer2D.style.overflow = 'hidden';
    viewer2D.style.position = 'relative';
    viewer2D.style.transform = 'translateY(-11.5rem)';
    viewer.appendChild(viewer2D);

    // Usando tu endpoint SVG; lo hacemos "responsive"
    fetch('/api/draw2d', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ smiles: mol.smiles })
    })
      .then(r => { if (!r.ok) throw new Error('Error al obtener imagen 2D'); return r.text(); })
      .then(svg => {
        viewer2D.innerHTML = svg;
        const svgEl = viewer2D.querySelector('svg');
        if (svgEl) {
          svgEl.setAttribute('width', '100%');
          svgEl.setAttribute('height', '100%');
          svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet');
          svgEl.style.width = '50%';
          svgEl.style.height = '50%';
          svgEl.style.display = 'block';
        }
      })
      .catch(err => {
        console.error("Error cargando visualización 2D:", err);
        viewer2D.textContent = "Error al mostrar estructura 2D.";
      });

    if (speedControl) speedControl.style.display = 'none';
  }

  // Ninguna vista activa
  else {
    const ph = document.createElement('div');
    ph.className = 'placeholder views-off';
    ph.style.cssText = 'display:flex;align-items:center;justify-content:center;width:100%;height:100%;color:#9ab8cc;font-size:.95rem;text-align:center;padding:1rem;';
    ph.textContent = 'Both views are off — turn on 3D or 2D (top right).';
    viewer.appendChild(ph);
    if (speedControl) speedControl.style.display = 'none';
  }

  // Barra de controles
  if (moleculeControls) {
    moleculeControls.style.display = 'flex';
    const total = Array.isArray(molecules) ? molecules.length : 0;
    document.getElementById('prev-molecule')?.style && (document.getElementById('prev-molecule').style.display = total > 1 ? 'inline-block' : 'none');
    document.getElementById('next-molecule')?.style && (document.getElementById('next-molecule').style.display = total > 1 ? 'inline-block' : 'none');
    updateNavigationButtons?.();
  }
}

function createBubbles(container, count = 15) {
    container.innerHTML = '';  // limpia burbujas anteriores
    for (let i = 0; i < count; i++) {
        const bubble = document.createElement('div');
        bubble.classList.add('bubble');
        bubble.style.left = `${Math.random() * 100}%`;
        const size = `${6 + Math.random() * 6}px`;
        bubble.style.width = size;
        bubble.style.height = size;
        bubble.style.animationDuration = `${3 + Math.random() * 2}s`;
        bubble.style.animationDelay = `${Math.random() * 5}s`;
        container.appendChild(bubble);
    }
}

function init3DMol() {
    // Verificar si 3Dmol está cargado
    if (window.$3Dmol) {
        console.log("3Dmol está cargado correctamente");
    } else {
        console.error("3Dmol no se cargó correctamente");
        // Podrías recargar la librería aquí si es necesario
    }
}

document.querySelectorAll('.mol-entry').forEach((entry, idx) => {
    entry.addEventListener('click', () => {
        selected.clear();
        selected.add(idx);

        // Remover estilo 'selected' de todas las entradas
        document.querySelectorAll('.mol-entry').forEach(e => e.classList.remove('selected'));
        entry.classList.add('selected');

        // Actualizar el índice y cambiar la visualización a 2D
        currentMoleculeIndex = idx;
        is2DEnabled = true;
        is3DEnabled = false;
        syncViewButtons();

        // Actualizar visualización
        updateViewerContainerLayout();
    });
});

// Funciones principales
// Limits the server enforces, shown in the page (the time limit used to accept 60 min while
// the server silently capped it at 20) + disable GLOMOS if the server cannot run it.
async function applyServerLimits() {
    try {
        const r = await fetch('/api/health');
        if (!r.ok) return;
        const h = await r.json();
        window.ELAYA_LIMITS = { maxAtoms: h.glomos_max_atoms, liteMin: h.lite_min_atoms, maxMinutes: h.max_minutes };
        window.dispatchEvent(new CustomEvent('elaya:limits'));
        const minutes = document.getElementById('glomos-minutes');
        if (minutes && Number.isFinite(h.max_minutes)) {
            minutes.max = String(h.max_minutes);
            if (Number(minutes.value) > h.max_minutes) minutes.value = String(h.max_minutes);
            minutes.title = `Server limit: ${h.max_minutes} min per job`;
        }
        const opt = document.querySelector('#post-optimization option[value="glomos"]');
        if (opt && h.glomos_ready === false) {
            opt.disabled = true;
            opt.textContent = 'GLOMOS (not available on this server)';
        }
    } catch (e) { /* offline: keep the defaults in the page */ }
}

// clamp the time limit to the field's max as the user types
document.addEventListener('DOMContentLoaded', () => {
    const minutes = document.getElementById('glomos-minutes');
    minutes?.addEventListener('change', () => {
        const max = Number(minutes.max) || 20, v = Number(minutes.value);
        if (v > max) { minutes.value = String(max); showError(`The server allows at most ${max} min per GLOMOS job.`); }
        if (v < 1) minutes.value = '1';
    });
});

async function checkBackendConnection() {
    try {
        console.log("Verificando conexión con el backend...");
        const response = await fetch(API_BASE_URL);
        if (!response.ok) {
            console.error('Error en el backend:', await response.text());
            showError('Error en el servidor backend');
        } else {
            const data = await response.json();
            console.log('Backend conectado:', data);
            applyServerLimits();          // silent: a toast on every visit was just noise
        }
    } catch (error) {
        console.error('Conexión fallida con el backend:', error);
        showError('<strong>Connection failed.</strong><br>Please try again.');
    }
}

// Reemplaza toda tu convertMolecules() por esta versión
// Reemplazo completo
async function convertMolecules(pickedList = null) {
  const convertBtn = document.getElementById('convert-molecules');
  const loader = convertBtn?.querySelector('.water-loader');
  const label  = convertBtn?.querySelector('.button-label');

  if (loader && label) {
    loader.style.display = 'block';
    label.style.opacity  = '0.3';
    convertBtn.disabled  = true;
    if (typeof createBubbles === 'function') createBubbles(loader);
  }

  try {
    // Determina el método actual (single/file)
    const selectedEl = document.querySelector('input[name="input-method"]:checked');
    const selectedMethod = selectedEl?.value?.trim().toLowerCase();

    // 1) Si viene una lista desde el modal, úsala tal cual
    if (Array.isArray(pickedList) && pickedList.length > 0) {
      window.molecules = pickedList;
      window.currentMoleculeIndex = 0;
      const smilesInput = document.getElementById('smiles');
      if (smilesInput) smilesInput.value = '';
    }
    // 2) Si el método es 'single', toma el texto
    else if (selectedMethod === 'single') {
      const smilesInput = document.getElementById('smiles');
      const smilesText  = smilesInput?.value?.trim();
      if (smilesText) {
        window.molecules = [{ smiles: smilesText, id: `mol_manual_${Date.now()}` }];
        window.currentMoleculeIndex = 0;
        if (typeof updateSmilesHistory === 'function') updateSmilesHistory(smilesText);
      }
    }

    // 3) Validación final
    if (!Array.isArray(window.molecules) || window.molecules.length === 0) {
      throw new Error('No molecules loaded to convert');
    }

    const method     = document.getElementById('conversion-method')?.value;
    const forceField = document.getElementById('force-field')?.value;
    const convertedMolecules = [];

    for (const mol of window.molecules) {
      const response = await fetch(`${API_BASE_URL}/convert`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          smiles: mol.smiles,
          identifier: mol.id,
          method,
          force_field: forceField
        })
      });

      if (!response.ok) {
        let errorText = 'Error during conversion';
        try { errorText = (await response.json())?.error || errorText; } catch {}
        throw new Error(errorText);
      }

      const data = await response.json();
      const xyzText  = extractXYZString(data.xyz ?? data.XYZ ?? data);
      const molBlock = (typeof data.mol === 'string') ? data.mol : (data.mol?.mol || null);

      convertedMolecules.push({
        ...mol,
        xyz: (xyzText || '').trim(),
        molBlock: molBlock || null,
        qa: {
          method: data.info?.method || method,
          approximate: !!data.approximate,
          stereo: data.stereo_qa || null,
          bonds: data.connectivity_check || null,
          rot: data.rotational_constants || null,
        }
      });

      const _smi = String(mol.smiles || '');
      showSuccess(`<strong>✔ Molecule successfully converted</strong><br><strong>SMILES:</strong> ${_esc(_smi.length > 70 ? _smi.slice(0, 67) + '…' : _smi)}`);
    }

    // Estado final + render/XYZ
    window.molecules = convertedMolecules;
    window.currentMoleculeIndex = 0;

    const currentMol = window.molecules[0];
    window.currentXYZ = currentMol.xyz || '';

    const formatTabBar = document.getElementById('format-tab-bar');
    if (formatTabBar) formatTabBar.style.display = 'flex';

    const hasXYZ = !!currentMol.xyz;
    const hasMol = !!currentMol.molBlock;
    // MOL/SDF carries bond orders (double/aromatic bonds are drawn); XYZ only has positions
    const format    = hasMol ? 'sdf' : 'xyz';
    const modelData = hasMol ? currentMol.molBlock : (hasXYZ ? currentMol.xyz : '');

    updateViewerContainerLayout();
    updateXYZDisplay();

    // Fuerza visibilidad del panel de XYZ
    const xyzDisplay = document.getElementById('xyz-display');
    if (xyzDisplay) xyzDisplay.style.display = 'block';

    // Reconstruye layout/controles
    try { updateViewerContainerLayout(); } catch {}
    updateNavigationButtons();
    populateIndividualDownloads?.();

    // Controles/botones
    const multiple       = window.molecules.length > 1;
    const prevBtn        = document.getElementById('prev-molecule');
    const nextBtn        = document.getElementById('next-molecule');
    const speedControl   = document.querySelector('.speed-control');
    const moleculeCtrls  = document.getElementById('molecule-controls');

    updateDownloadButtons();
    if (moleculeCtrls) {
      if (prevBtn) prevBtn.style.display = multiple ? 'inline-block' : 'none';
      if (nextBtn) nextBtn.style.display = multiple ? 'inline-block' : 'none';
      if (speedControl) speedControl.style.display = 'flex';
      moleculeCtrls.style.display = 'flex';
    }
  } catch (error) {
    console.error("Error in convertMolecules:", error);
    showError(`Error converting molecule: ${error.message}`);
  } finally {
    if (loader && label) {
      loader.style.display = 'none';
      label.style.opacity  = '1';
      convertBtn.disabled  = false;
      loader.innerHTML     = '';
    }
    updateNavigationButtons();
    updateDownloadButtons();
  }
}

function insertTitleLine(xyz, title) {
    const lines = xyz.trim().split('\n');
    if (lines.length < 2) return xyz;
    lines[1] = title;
    return lines.join('\n');
}

async function convertSingleMolecule() {
  // Grab button refs here so finally() can always unlock the UI
  const _convertBtn = document.getElementById('convert-molecules');
  const _loader     = _convertBtn?.querySelector('.water-loader');
  const _label      = _convertBtn?.querySelector('.button-label');

  try {
    // v2.4.7: always convert what is in the box now. `molecules` here is a different binding from
    // window.molecules, and it kept the previous molecule, so a second conversion re-used the old SMILES.
    const _inputSmiles = document.getElementById('smiles')?.value?.trim();
    if (_inputSmiles) {
      molecules = [{ smiles: _inputSmiles, id: _inputSmiles }];
      currentMoleculeIndex = 0;
    } else if (!Array.isArray(molecules) || molecules.length === 0 || !molecules[currentMoleculeIndex]) {
      throw new Error('No molecule selected. Please enter a SMILES string.');
    }

    const method     = document.getElementById('conversion-method')?.value || 'rdkit';
    const forceField = document.getElementById('force-field')?.value || 'UFF';
    const molecule   = molecules[currentMoleculeIndex];

    // GLOMOS is handled by the streaming path – never run a blocking fetch for it
    const postOpt = document.getElementById("post-optimization")?.value || null;
    if (postOpt === "glomos") return;

    const response = await fetch(`${API_BASE_URL}/convert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        smiles: molecule.smiles,
        identifier: molecule.id,
        method,
        force_field: forceField,
        post_opt: null,
        glomos_params: null
      })
    });

    if (!response.ok) {
      let serverErr = 'Error en la conversión';
      try {
        const e = await response.json();
        if (e?.error) serverErr = e.error;
      } catch {}
      throw new Error(serverErr);
    }

    const data = await response.json();

    const xyzText =
      (typeof data?.xyz === 'string' && data.xyz) ? data.xyz :
      (data?.xyz && typeof data.xyz.xyz === 'string' ? data.xyz.xyz : '');

    if (!xyzText) throw new Error('No se recibieron datos XYZ del servidor');

    const titleLine     = `0  0   ${molecule.smiles}`;
    const xyzWithHeader = insertTitleLine(xyzText, titleLine);
    currentXYZ = xyzWithHeader;

    const molText =
      (typeof data?.mol === 'string' && data.mol) ? data.mol :
      (data?.mol && typeof data.mol.mol === 'string' ? data.mol.mol : '');

    molecules[currentMoleculeIndex] = {
      ...molecules[currentMoleculeIndex],
      xyz: xyzWithHeader,
      molBlock: molText || null,
      qa: {
        method: data.info?.method || method,
        approximate: !!data.approximate,
        stereo: data.stereo_qa || null,
        bonds: data.connectivity_check || null,
        rot: data.rotational_constants || null,
      }
    };

    updateXYZDisplay?.();
    const xyzDisplay = document.getElementById('xyz-display');
    if (xyzDisplay) xyzDisplay.style.display = 'block';

    updateViewerContainerLayout();
    const _s = String(molecule.smiles || '');
    showSuccess?.(`<strong>✔ Molecule successfully converted</strong><br><strong>SMILES:</strong> ${_esc(_s.length > 70 ? _s.slice(0, 67) + '…' : _s)}`);

    const moleculeCtrls = document.getElementById('molecule-controls');
    const speedControl  = document.querySelector('.speed-control');
    if (moleculeCtrls) moleculeCtrls.style.display = 'flex';
    if (speedControl)  speedControl.style.display  = is3DEnabled ? 'flex' : 'none';

    updateDownloadButtons?.();
    updateNavigationButtons?.();

  } catch (err) {
    console.error(err);
    showError?.(err?.message || 'Unexpected error during conversion');
  } finally {
    // Always unlock the button, no matter what happened
    if (_loader && _label) {
      _loader.style.display = 'none';
      _label.style.opacity  = '1';
      _loader.innerHTML     = '';
    }
    if (_convertBtn) _convertBtn.disabled = false;
  }
}

// Compact quality line under the viewer: stereo / bonds checks from the backend, rotational constants
function renderStructureQA() {
    const xyzDisplay = document.getElementById('xyz-display');
    if (!xyzDisplay) return;
    let box = document.getElementById('structure-qa');
    if (!box) {
        box = document.createElement('div');
        box.id = 'structure-qa';
        xyzDisplay.parentNode.insertBefore(box, xyzDisplay);
    }
    // results live either in `molecules` or in window.molecules (two different bindings in this file):
    // use the entry whose XYZ is the one on screen, so a GLOMOS conformer never shows stale checks
    const shown = String((typeof currentXYZ === 'string' && currentXYZ) || window.currentXYZ || '').trim();
    const cands = [];
    for (const [list, i] of [[molecules, currentMoleculeIndex], [window.molecules, window.currentMoleculeIndex]]) {
        if (Array.isArray(list) && list[Number.isInteger(i) ? i : 0]) cands.push(list[Number.isInteger(i) ? i : 0]);
    }
    const cur = cands.find(m => m.qa && !m.glomos && String(m.xyz || '').trim() === shown);
    const qa = cur ? cur.qa : null;
    if (!qa || window.ELAYA_GLOMOS_RUNNING) { box.style.display = 'none'; box.innerHTML = ''; return; }
    const esc = t => String(t).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
    // v2.4.4: only problems are shown; when everything matches the SMILES nothing is added
    const chips = [];
    if (qa.approximate) chips.push(`<span class="qa-chip warn" title="NetworkX builds a graph layout, not a force-field geometry">Approximate layout (NetworkX)</span>`);
    if (qa.stereo && !qa.stereo.ok) {
        chips.push(`<span class="qa-chip bad" title="${esc((qa.stereo.problems || []).join('\n'))}">Stereo differs from the SMILES: ${esc((qa.stereo.problems || [])[0] || '')}</span>`);
    }
    if (qa.bonds && qa.bonds.ok === false) {
        chips.push(`<span class="qa-chip warn" title="${esc(qa.bonds.detail || '')}">Some bond lengths look off</span>`);
    }
    box.innerHTML = chips.join('');
    box.style.display = chips.length ? 'flex' : 'none';
}

function updateXYZDisplay() {
    const xyzDisplay = document.getElementById('xyz-display');
    if (!xyzDisplay) return;
    try { renderStructureQA(); } catch (e) { /* never block the XYZ panel */ }

    const raw = (currentXYZ || '').trim();
    if (!raw) { xyzDisplay.style.display = 'none'; return; }

    const lines = raw.split('\n');
    xyzDisplay.style.display = 'block';

    if (lines.length < 3) {
        xyzDisplay.textContent = raw;
        return;
    }

    // Standard XYZ: line 0 = atom count, line 1 = comment, rest = coords
    const atomCount = lines[0].trim();
    const comment   = lines[1] || '';

    const atoms = lines.slice(2).map(line => {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 4) {
            const sym = parts[0].padEnd(2);
            const x   = parseFloat(parts[1]).toFixed(4).padStart(10);
            const y   = parseFloat(parts[2]).toFixed(4).padStart(10);
            const z   = parseFloat(parts[3]).toFixed(4).padStart(10);
            return `${sym}  ${x}  ${y}  ${z}`;
        }
        return line;
    });

    xyzDisplay.textContent = [atomCount, comment, ...atoms].join('\n');
}

// 3Dmol's zoomTo() fits the molecule to the panel height; in a narrow panel (3D + 2D side by side,
// phones) that crops it left and right. Shrink by the aspect ratio so the whole molecule is visible.
function fitWhole(viewer) {
    viewer.zoomTo();
    const c = viewer.getCanvas ? viewer.getCanvas() : null;
    const w = c ? c.clientWidth : 0, h = c ? c.clientHeight : 0;
    viewer.zoom(0.9 * (w && h ? Math.min(1, w / h) : 1));
}
window.elayaFitWhole = fitWhole;

function render3DMolecule(modelData, smiles = '', format = 'xyz', targetContainer = viewerContainer) {
    if (!targetContainer) {
        viewerContainer = document.getElementById('viewer-container') || null;
        targetContainer = viewerContainer;
    }

    if (!targetContainer) {
        console.error("⚠ targetContainer no está definido.");
        return;
    }

    // Cancelar animación previa si existe
    if (rotationAnimationId) {
        cancelAnimationFrame(rotationAnimationId);
        rotationAnimationId = null;
    }

    // Limpiar contenedor y actualizar título
    targetContainer.innerHTML = '';
    if (moleculeTitle) {
        moleculeTitle.textContent = smiles;
        moleculeTitle.style.display = 'block';
    }

    // Verificar si 3Dmol está disponible
    if (!window.$3Dmol || !window.$3Dmol.createViewer) {
        targetContainer.innerHTML = `
            <div class="placeholder error">
                Error: La biblioteca 3Dmol no está disponible
            </div>
        `;
        return;
    }

    // ── Defer WebGL init until the container has real pixel dimensions ──────
    // Calling $3Dmol.createViewer on a 0×0 element triggers GL_INVALID_FRAMEBUFFER_OPERATION.
    // We retry via requestAnimationFrame until the browser has painted the layout.
    function _initViewer() {
        const w = targetContainer.offsetWidth;
        const h = targetContainer.offsetHeight;

        if (w === 0 || h === 0) {
            _initViewer._retries = (_initViewer._retries || 0) + 1;
            if (_initViewer._retries < 20) {     // up to ~330 ms at 60 fps
                requestAnimationFrame(_initViewer);
                return;
            }
            // Fallback: force an explicit height so WebGL can allocate the framebuffer
            if (!targetContainer.style.height) targetContainer.style.height = '400px';
        }

        const viewerW = targetContainer.offsetWidth  || 500;
        const viewerH = targetContainer.offsetHeight || 400;

        let viewer;
        try {
            viewer = $3Dmol.createViewer(targetContainer, {
                width: viewerW,
                height: viewerH,
                preserveDrawingBuffer: true,      // lets Image/Record copy the 3D canvas next to the 2D drawing
                backgroundColor: 'black'
            });
        } catch (e) {
            console.error("❌ Error al crear viewer 3Dmol:", e);
            targetContainer.innerHTML = '<div class="placeholder error">Error al inicializar visor 3D</div>';
            return;
        }

        const isVisible = () => !document.hidden && targetContainer.offsetWidth > 0 && targetContainer.offsetHeight > 0;

        try {
            viewer.addModel(modelData, format, { keepH: true, noComputeSecondaryStructure: true });
            viewer.setStyle({}, { stick: { radius: 0.15 }, sphere: { scale: 0.25 } });
            fitWhole(viewer);                       // whole molecule with a small margin
            if (isVisible()) viewer.render();      // a hidden (0×0) canvas would raise WebGL errors
        } catch (e) {
            console.error("❌ Error al renderizar modelo:", e);
            targetContainer.innerHTML = '<div class="placeholder error">Error al renderizar molécula</div>';
            return;
        }

        // Skip frames while the viewer is hidden (another section shown, panel collapsed, tab in
        // background): rendering into a 0×0 canvas floods the console with
        // GL_INVALID_FRAMEBUFFER_OPERATION. Resize once when it becomes visible again.
        let wasHidden = !isVisible();
        const animate = () => {
            if (!isVisible()) {
                wasHidden = true;
            } else {
                if (wasHidden) {
                    wasHidden = false;
                    // zoom computed while the canvas was 0×0 is meaningless: redo it now
                    try { viewer.resize(); fitWhole(viewer); } catch (e) { /* ignore */ }
                }
                if (!isRotationPaused) {
                    viewer.rotate(rotationSpeed, { x: 0, y: 1, z: 0 });
                    viewer.render();
                }
            }
            rotationAnimationId = requestAnimationFrame(animate);
        };
        animate();

        currentVisualizations = [viewer];

        const placeholder = document.querySelector('.placeholder');
        if (placeholder) placeholder.style.display = 'none';

        setTimeout(() => {
            try { if (isVisible()) { viewer.resize(); fitWhole(viewer); viewer.render(); } }
            catch (err) { console.warn("⚠ Error al redibujar viewer:", err); }
        }, 150);
    }

    requestAnimationFrame(_initViewer);
}

function navigateMolecules(direction) {
  const newIndex = currentMoleculeIndex + direction;

  if (newIndex < 0 || newIndex >= molecules.length) {
    console.warn('⚠ Invalid molecule navigation index:', newIndex);
    return;
  }

  currentMoleculeIndex = newIndex;
  const mol = molecules[newIndex];
  if (!mol) {
    console.warn('⚠ No molecule data found at index:', newIndex);
    return;
  }

  // Actualiza el XYZ global para el panel
  currentXYZ = mol.xyz || '';

  // 🔁 Render SIEMPRE a través del layout (se encargará de 2D/3D)
  updateViewerContainerLayout();

  // Refresca vistas auxiliares y controles
  updateXYZDisplay?.();
  updateNavigationButtons?.();
  updateDownloadButtons?.();

  const moleculeCtrls = document.getElementById('molecule-controls');
  const speedControl  = document.querySelector('.speed-control');
  if (moleculeCtrls) moleculeCtrls.style.display = 'flex';
  if (speedControl)  speedControl.style.display  = is3DEnabled ? 'flex' : 'none';
}

function toggleRotation() {
    isRotationPaused = !isRotationPaused;
    const btn = document.getElementById('pause-btn');
    if (btn) {
        btn.textContent = isRotationPaused ? 'Reanudar' : 'Pausar';
    }
}

function changeRotationSpeed(speed) {
    rotationSpeed = parseFloat(speed);
}

// ── Fullscreen ───────────────────────────────────────────────────────────────
// Strategy: requestFullscreen on the card div.
// The controls bar is injected with position:absolute + very high z-index.
// viewer-container height is reduced so the bar is not covered.

function _buildFsBar() {
  document.getElementById('fs-controls-bar')?.remove();

  const is2D  = is2DEnabled && !is3DEnabled;
  const multi = Array.isArray(molecules) && molecules.length > 1;
  const spd   = document.getElementById('rotation-speed')?.value ?? rotationSpeed;
  const bg    = is2D ? 'rgba(12,22,52,0.94)' : 'rgba(0,0,0,0.86)';

  const bar = document.createElement('div');
  bar.id = 'fs-controls-bar';
  // Use inline style only — no class conflicts
  bar.setAttribute('style', [
    'position:absolute',
    'bottom:0',
    'left:0',
    'right:0',
    'width:100%',
    'height:52px',
    `background:${bg}`,
    'display:flex',
    'align-items:center',
    'justify-content:space-between',
    'padding:0 24px',
    'box-sizing:border-box',
    'z-index:999999',
    'font-family:Inter,system-ui,sans-serif',
    'backdrop-filter:blur(6px)',
    'border-top:1px solid rgba(255,255,255,0.08)',
  ].join(';'));

  bar.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;color:#cce0ff;font-size:0.88rem;flex-shrink:0;">
      <span style="white-space:nowrap;">Speed</span>
      <input id="fs-speed-input" type="range" min="0" max="5" step="0.5" value="${spd}"
        style="width:120px;accent-color:#3cb49a;cursor:pointer;vertical-align:middle;">
    </div>
    <div style="display:flex;align-items:center;gap:10px;flex-shrink:0;">
      <button id="fs-exit-btn" title="Exit Fullscreen"
        style="background:transparent;border:none;cursor:pointer;padding:5px;display:flex;align-items:center;opacity:0.85;">
        <svg viewBox="0 0 24 24" width="22" height="22" fill="white" xmlns="http://www.w3.org/2000/svg">
          <path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/>
        </svg>
      </button>
      <button id="fs-prev-btn"
        style="display:${multi?'inline-flex':'none'};align-items:center;
               padding:5px 16px;background:rgba(40,90,200,0.65);border:none;
               border-radius:8px;color:#fff;cursor:pointer;font-size:0.88rem;">← Back</button>
      <button id="fs-next-btn"
        style="display:${multi?'inline-flex':'none'};align-items:center;
               padding:5px 16px;background:rgba(40,90,200,0.65);border:none;
               border-radius:8px;color:#fff;cursor:pointer;font-size:0.88rem;">Next →</button>
    </div>`;

  bar.querySelector('#fs-speed-input').addEventListener('input', e => {
    rotationSpeed = parseFloat(e.target.value);
    const orig = document.getElementById('rotation-speed');
    if (orig) orig.value = e.target.value;
  });
  bar.querySelector('#fs-exit-btn').addEventListener('click', () => document.exitFullscreen());
  bar.querySelector('#fs-prev-btn').addEventListener('click', () => navigateMolecules(-1));
  bar.querySelector('#fs-next-btn').addEventListener('click', () => navigateMolecules(1));

  return bar;
}

function toggleVisualizationFullscreen() {
  const card = document.querySelector('.visualization-container');
  if (!card) return;
  if (!document.fullscreenElement) {
    card.requestFullscreen().catch(e => console.warn('FS failed:', e));
  } else {
    document.exitFullscreen();
  }
}

document.addEventListener('fullscreenchange', () => {
  const isFs = !!document.fullscreenElement;
  const card = document.querySelector('.visualization-container');
  const vc   = document.getElementById('viewer-container');
  const fsBtn= document.getElementById('fullscreen-btn');

  if (isFs && card) {
    // card is now the fullscreen viewport — make sure it is position:relative
    // so absolute children are contained within it
    card.style.setProperty('position', 'relative', 'important');
    card.style.setProperty('overflow', 'visible', 'important'); // allow bar to paint

    // Shrink viewer-container to leave room for the 52px bar
    if (vc) {
      vc._fsOrigHeight = vc.style.height;
      vc.style.setProperty('height', 'calc(100% - 52px)', 'important');
    }

    // Append bar as last child of the fullscreen element (paints on top)
    card.appendChild(_buildFsBar());

  } else {
    // Restore
    document.getElementById('fs-controls-bar')?.remove();
    if (vc && vc._fsOrigHeight !== undefined) {
      vc.style.height = vc._fsOrigHeight;
    }
    if (card) {
      card.style.removeProperty('overflow');
      card.style.removeProperty('position');   // back to the stylesheet (sticky on desktop)
    }
    // the canvas was sized for the whole screen: fit it to the card again
    setTimeout(() => { try { window.elayaFitViewer?.(); } catch (e) { /* */ } }, 150);
  }

  // Swap in-page button icon
  if (fsBtn) {
    fsBtn.innerHTML = isFs
      ? '<svg viewBox="0 0 24 24" width="18" height="18" fill="white"><path d="M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z"/></svg>'
      : '<svg viewBox="0 0 24 24" width="18" height="18" fill="white"><path d="M3 3h6v2H5v4H3V3zm12 0h6v6h-2V5h-4V3zM3 13h2v4h4v2H3v-6zm16 4h-4v2h6v-6h-2v4z"/></svg>';
  }
});

document.addEventListener('click', function (event) {
    const overlay = document.getElementById('modal-overlay');
    const content = document.querySelector('.modal-content');

    // Si no está abierto el modal, no hacemos nada
    if (!overlay || overlay.style.display === 'none') return;

    // Si se hizo clic fuera del modal-content, cerramos
    if (!event.target.closest('.modal-content')) {
        overlay.style.display = 'none';
    }
});

// Cierre directo desde botón Cancel
const cancelButton = document.getElementById('cancel-button');
if (cancelButton) {
    cancelButton.addEventListener('click', () => {
        const overlay = document.getElementById('modal-overlay');
        if (overlay) overlay.style.display = 'none';
    });
}

function downloadXYZ() {
    if (!currentXYZ) {
        showError('No hay datos XYZ para descargar');
        return;
    }

    try {
        const formattedXYZ = formatXYZWithAlignment(currentXYZ);
        const blob = new Blob([formattedXYZ], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const smilesName = molecules[currentMoleculeIndex]?.smiles || 'unknown';
        const safeName = smilesName.replace(/[\\/:*?"<>|]/g, '_'); 
        a.download = `${safeName}.xyz`;                 
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showSuccess('✔ XYZ file downloaded');
    } catch (error) {
        console.error("Error al descargar XYZ:", error);
        showError('Error al descargar el archivo XYZ');
    }
}

async function downloadImage() {
    // v2.4.8: with 2D on, save what is on screen (2D, or 3D + 2D side by side)
    if (is2DEnabled && window.ElayaView2D && document.querySelector('#viewer-2d svg')) {
        try {
            const cv = await window.ElayaView2D.snapshot();
            const a = document.createElement('a');
            a.href = cv.toDataURL('image/png');
            a.download = `molecule_${molecules[currentMoleculeIndex]?.id || 'unknown'}${is3DEnabled ? '_3D_2D' : '_2D'}.png`;
            document.body.appendChild(a); a.click(); a.remove();
            showSuccess('✔ Downloaded image');
        } catch (e) { console.error(e); showError('Could not save the image'); }
        return;
    }
    if (!currentVisualizations.length) {
        showError('No hay visualización para descargar');
        return;
    }

    try {
        const viewer = currentVisualizations[0];
        const imgData = viewer.pngURI();
        const a = document.createElement('a');
        a.href = imgData;
        a.download = `molecule_${molecules[currentMoleculeIndex]?.id || 'unknown'}.png`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        showSuccess('✔ Downloaded image');
    } catch (error) {
        console.error("Error al descargar imagen:", error);
        showError('Error al descargar la imagen');
    }
}
function toggleInputMethod() {
    try {
        const selected = document.querySelector('input[name="input-method"]:checked');
        if (!selected) {
            console.warn("⚠ No se encontró el radio seleccionado");
            return;
        }

        const method = selected.value;

        const singleInput = document.getElementById('single-input');
        const fileInput = document.getElementById('file-input');
        const loadButton = document.getElementById('load-smiles');
        const fileFormatExample = document.getElementById('file-format-example');

        if (singleInput) singleInput.style.display = method === 'single' ? 'block' : 'none';
        if (fileInput) fileInput.style.display = method === 'file' ? 'block' : 'none';
        if (fileFormatExample) fileFormatExample.style.display = method === 'file' ? 'block' : 'none';

        if (loadButton) {
            if (method === 'single') {
                loadButton.style.display = 'inline-block';
                loadButton.disabled = false;
            } else {
                loadButton.style.display = 'none';
            }
        }

    } catch (error) {
        console.error("⚠ Error en toggleInputMethod:", error);
    }
}

async function loadSmiles(showConfirmation = true) {
    try {
        console.log("Iniciando carga de SMILES...");
        if (moleculeControls) {
            const prevBtn = document.getElementById('prev-molecule');
            const nextBtn = document.getElementById('next-molecule');
            const speedControl = document.querySelector('.speed-control');
            const moleculeControls = document.getElementById('molecule-controls');
        
            if (molecules.length > 1) {
                moleculeControls.style.display = 'flex';
                if (prevBtn) prevBtn.style.display = 'inline-block';
                if (nextBtn) nextBtn.style.display = 'inline-block';
            } else {
                moleculeControls.style.display = 'flex'; // Mantener visible la barra
                if (prevBtn) prevBtn.style.display = 'none';
                if (nextBtn) nextBtn.style.display = 'none';
            }
        
            if (speedControl) speedControl.style.display = 'flex'; // Asegurar visibilidad
        }       
        const method = document.querySelector('input[name="input-method"]:checked').value;
        console.log("Método seleccionado:", method);

        if (method === 'single') {
            const smiles = document.getElementById('smiles').value.trim();
            console.log("SMILES ingresado:", smiles);
            updateSmilesHistory(smiles);

            if (!smiles) {
                throw new Error('Por favor ingrese un string SMILES');
            }
            molecules = [{ smiles, id: smiles }];

        } else {
            const fileInput = document.getElementById('smiles-file');
            console.log("Archivo seleccionado:", fileInput?.files[0]);

            if (!fileInput?.files?.length) {
                throw new Error('Por favor seleccione un archivo');
            }

            const text = await fileInput.files[0].text();
            molecules = [];
            console.log("Contenido del archivo:", text);

            text.split('\n').forEach(line => {
                const trimmedLine = line.trim();
                if (trimmedLine) {
                    const parts = trimmedLine.split(/\s+/);
                    if (parts.length >= 1) {
                        const smiles = parts[0];
                        const id = parts.length >= 2 ? parts[1] : `mol_${molecules.length + 1}`;
                        molecules.push({ smiles, id });
                    }
                }
            });

            if (molecules.length === 0) {
                throw new Error('El archivo no contiene moléculas válidas');
            }
        }
        
        console.log("Moléculas cargadas:", molecules);
        const loadConfirmation = document.getElementById('load-confirmation');

        if (loadConfirmation && showConfirmation) {
            const moleculeInfo = molecules.map(mol => 
                `<div><strong>SMILE:</strong> ${mol.smiles}</div>`
            ).join('<hr>');
            loadConfirmation.innerHTML = `
                <div class="alert success" style="text-align: left; padding: 10px 15px;">
                    <strong>${molecules.length === 1 ? 'Molécula cargada exitosamente:' : `${molecules.length} moléculas cargadas exitosamente:`}</strong><br>
                    ${moleculeInfo}
                </div>
            `;
            loadConfirmation.style.display = 'block';
            setTimeout(() => {
                loadConfirmation.style.display = 'none';
            }, 5000);
        }

        const convertBtn = document.getElementById('convert-molecules');
        if (convertBtn) {
            convertBtn.disabled = false;
            console.log("Botón Convert habilitado");
        }
    } catch (error) {
        console.error("Error en loadSmiles:", error);
        showError(`Error al cargar SMILES: ${error.message}`);
        throw error;
    }
}

function toggleForceField() {
    const method = document.getElementById('conversion-method')?.value;
    const forceFieldDiv = document.getElementById('force-field-options');

    if (!method || !forceFieldDiv) {
        console.debug("toggleForceField: DOM not ready yet");
        return;
    }

    if (method === 'networkx' || method === 'auto3d') {
        forceFieldDiv.style.display = 'none';
    } else {
        forceFieldDiv.style.display = 'block';
    }
}

function retryVisualization() {
    if (currentXYZ && molecules[currentMoleculeIndex]) {
        render3DMolecule(currentXYZ, molecules[currentMoleculeIndex].smiles);
    }
}

function formatXYZWithAlignment(xyzText) {
    const lines = xyzText.trim().split('\n');
    if (lines.length < 3) return xyzText;

    // Standard XYZ format: line 0 = atom count, line 1 = comment, lines 2+ = atom coords
    const atomCount = lines[0].trim();
    const comment   = lines[1];          // preserve exactly as-is (SMILES title etc.)
    const atomLines = lines.slice(2).map(line => {
        const parts = line.trim().split(/\s+/);
        if (parts.length >= 4) {
            const sym = parts[0];
            const x   = parseFloat(parts[1]).toFixed(4);
            const y   = parseFloat(parts[2]).toFixed(4);
            const z   = parseFloat(parts[3]).toFixed(4);
            // Align columns: symbol left-padded 2, coords right-aligned in 10-char fields
            return `${sym.padEnd(2)}  ${x.padStart(10)}  ${y.padStart(10)}  ${z.padStart(10)}`;
        }
        return line;
    });

    return [atomCount, comment, ...atomLines].join('\n');
}

// Funciones de ayuda
function _esc(t) { return String(t ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
// Notifications live in one stack at the top, in the space of the page title
function _toastStack() {
    let stack = document.getElementById('toast-stack');
    if (!stack) {
        stack = document.createElement('div');
        stack.id = 'toast-stack';
        stack.setAttribute('role', 'status');
        stack.setAttribute('aria-live', 'polite');
        document.body.appendChild(stack);
    }
    return stack;
}

function _toast(div, ms) {
    div.title = 'Click to dismiss';
    div.addEventListener('click', () => div.remove());
    const stack = _toastStack();
    stack.appendChild(div);
    while (stack.children.length > 3) stack.firstElementChild.remove();
    setTimeout(() => div.remove(), ms);
}

function showSuccess(message) {
    console.log("Mostrando mensaje de éxito:", message);
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert success';
    alertDiv.innerHTML = message;
    _toast(alertDiv, 3500);
}

function showError(message) {
    console.error("Mostrando mensaje de error:", message);
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert error';
    const [first, ...rest] = message.split(':');
    const formattedMessage = rest.length
        ? `⚠ <strong>${first}:</strong><br>${rest.join(':').trim()}`
        : `⚠ ${message}`;

    alertDiv.innerHTML = formattedMessage;
    alertDiv.setAttribute('role', 'alert');
    _toast(alertDiv, 8000);
}

// Antes: async function showMoleculeSelectionModal() {
async function showMoleculeSelectionModal(moleculeList) {
  return new Promise((resolve) => {
    let selected = new Set();
    let focusedIndex = 0;
    let shiftAnchor = null;
    let lastClicked = null;

    // ¡No uses el modal global! Crea uno local aquí:
    const modal = document.createElement('div');
    modal.id = 'molecule-selection-modal';   
    modal.className = 'modal-overlay';
    modal.style.cssText = `
      position:fixed; inset:0; background:rgba(0,0,0,.7); z-index:2000;
      display:flex; align-items:center; justify-content:center; font-family:Inter,system-ui;
    `;

    const box = document.createElement('div');
    box.className = 'modal-content';
    box.tabIndex = 0;
    box.style.cssText = `
      background:#12122B; color:#f5f5f5; width:min(720px,92vw); max-height:80vh;
      border-radius:12px; padding:16px; outline:none; display:flex; flex-direction:column; gap:12px;
    `;

    const header = document.createElement('div');
    header.style.cssText = 'display:flex; align-items:center; justify-content:space-between; gap:12px;';

    const title = document.createElement('h3');
    title.textContent = 'Select SMILES to convert';
    title.style.margin = '0';

    const selectAllLabel = document.createElement('label');
    selectAllLabel.style.cssText = 'display:flex; align-items:center; gap:8px; cursor:pointer; font-weight:600;';
    selectAllLabel.innerHTML = `<input id="sel-all" type="checkbox" style="transform:scale(1.2)"/> Select all`;

    header.appendChild(title);
    header.appendChild(selectAllLabel);

    const list = document.createElement('div');
    list.id = 'molecule-list';
    list.style.cssText = `
      border:1px solid #243149; border-radius:10px; overflow:auto; max-height:56vh;
      display:flex; flex-direction:column;
    `;

    // Render items desde moleculeList (NO desde 'molecules')
    moleculeList.forEach((mol, i) => {
      const row = document.createElement('div');
      row.className = 'mol-row';
      row.dataset.index = i;
      row.style.cssText = `
        padding:8px 10px; border-bottom:1px solid #0f697533; cursor:pointer;
        display:flex; align-items:center; gap:10px; user-select:none;
      `;
      row.innerHTML = `
        <input type="checkbox" class="chk" aria-label="select row ${i}" />
        <div style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
          <strong>${mol.id}</strong>: ${mol.smiles}
        </div>
      `;
      list.appendChild(row);
    });

    const footer = document.createElement('div');
    footer.style.cssText = 'display:flex; justify-content:flex-end; gap:10px;';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText = 'background:#612020b0; color:#fff; border:none; border-radius:10px; padding:8px 14px; cursor:pointer;';

    const confirmBtn = document.createElement('button');
    confirmBtn.textContent = 'Convert selected';
    confirmBtn.style.cssText = 'background:linear-gradient(135deg,#9D4EDD,rgb(60,180,154)); color:#fff; border:none; border-radius:10px; padding:8px 14px; cursor:pointer;';

    footer.appendChild(cancelBtn);
    footer.appendChild(confirmBtn);

    box.appendChild(header);
    box.appendChild(list);
    box.appendChild(footer);
    modal.appendChild(box);
    document.body.appendChild(modal);

    const rows = [...list.querySelectorAll('.mol-row')];
    const chks = [...list.querySelectorAll('.mol-row .chk')];
    const selAll = selectAllLabel.querySelector('#sel-all');

    function paint() {
      rows.forEach((r, i) => {
        const isSel = selected.has(i);
        const isFocus = i === focusedIndex;
        r.style.background = isSel ? '#1e2a44' : 'transparent';
        r.style.outline = isFocus ? '1px solid #5aa9e6' : 'none';
        r.style.outlineOffset = isFocus ? '-1px' : '0';
        chks[i].checked = isSel;
      });
      selAll.checked = selected.size === rows.length;
      if (focusedIndex >= 0) rows[focusedIndex].scrollIntoView({ block: 'nearest' });
    }

    function selectRange(a, b) {
      const [s, e] = [Math.min(a, b), Math.max(a, b)];
      selected.clear();
      for (let i = s; i <= e; i++) selected.add(i);
      paint();
    }

    function toggleIndex(i) {
      if (selected.has(i)) selected.delete(i); else selected.add(i);
      paint();
    }

    rows.forEach((row, i) => {
      row.addEventListener('click', (ev) => {
        focusedIndex = i;
        if (ev.shiftKey && lastClicked != null) {
          shiftAnchor = lastClicked;
          selectRange(shiftAnchor, i);
        } else if (ev.metaKey || ev.ctrlKey) {
          toggleIndex(i);
          lastClicked = i;
          shiftAnchor = i;
        } else {
          selected.clear();
          selected.add(i);
          lastClicked = i;
          shiftAnchor = i;
          paint();
        }
      });
      row.querySelector('.chk').addEventListener('click', (ev) => {
        ev.stopPropagation();
        if (ev.shiftKey && lastClicked != null) {
          shiftAnchor = lastClicked;
          selectRange(shiftAnchor, i);
        } else {
          toggleIndex(i);
          lastClicked = i;
          shiftAnchor = i;
        }
      });
    });

    selAll.addEventListener('change', () => {
      if (selAll.checked) {
        selected = new Set(rows.map((_, i) => i));
      } else {
        selected.clear();
      }
      paint();
    });

    function onKey(e) {
      const max = rows.length - 1;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        const old = focusedIndex;
        focusedIndex += (e.key === 'ArrowDown' ? 1 : -1);
        focusedIndex = Math.max(0, Math.min(max, focusedIndex));
        if (e.shiftKey) {
          if (shiftAnchor == null) shiftAnchor = old;
          selectRange(shiftAnchor, focusedIndex);
        } else {
          shiftAnchor = null;
          paint();
        }
      } else if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        toggleIndex(focusedIndex);
        if (lastClicked == null) lastClicked = focusedIndex;
      } else if (e.key === 'Enter') {
        finish(true);
      } else if (e.key === 'Escape') {
        finish(false);
      }
    }

    function finish(ok) {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('click', onOutside);
      document.body.removeChild(modal);
      resolve(ok ? selected : null);
    }

    // Cerrar al hacer clic fuera del contenido (dentro de la MISMA función)
    function onOutside(e) {
      if (!box.contains(e.target)) finish(false);
    }

    cancelBtn.addEventListener('click', () => finish(false));
    confirmBtn.addEventListener('click', () => finish(true));
    document.addEventListener('keydown', onKey);
    setTimeout(() => document.addEventListener('click', onOutside), 0);

    paint();
    box.focus();
  });
}

window.showMoleculeSelectionModal = showMoleculeSelectionModal;

function updateSmilesHistory(newSmiles) {
    const key = 'smilesHistory';
    let history = JSON.parse(sessionStorage.getItem(key)) || [];

    // Elimina duplicados y agrega nuevo al principio
    history = [newSmiles, ...history.filter(s => s !== newSmiles)];

    // Limita a 5 entradas
    history = history.slice(0, 5);

    // Guarda en sessionStorage
    sessionStorage.setItem(key, JSON.stringify(history));

    // Actualiza el datalist
    const datalist = document.getElementById('smiles-history');
    datalist.innerHTML = '';
    history.forEach(smiles => {
        const option = document.createElement('option');
        option.value = smiles;
        datalist.appendChild(option);
    });
}

function loadSmilesHistory() {
    const key = 'smilesHistory';
    const history = JSON.parse(sessionStorage.getItem(key)) || [];
    const datalist = document.getElementById('smiles-history');
    if (datalist) {
        datalist.innerHTML = '';
        history.forEach(smiles => {
            const option = document.createElement('option');
            option.value = smiles;
            datalist.appendChild(option);
        });
    }
}

function updateNavigationButtons() {
  const prevBtn = document.getElementById('prev-molecule');
  const nextBtn = document.getElementById('next-molecule');
  const ctrls   = document.getElementById('molecule-controls');
  const speed   = document.querySelector('.speed-control');

  const total = Array.isArray(window.molecules) ? window.molecules.length : 0;
  const i     = typeof window.currentMoleculeIndex === 'number' ? window.currentMoleculeIndex : 0;

  // Mostrar la barra si hay al menos una molécula
  if (ctrls) ctrls.style.display = total > 0 ? 'flex' : 'none';

  // Mostrar el deslizador solo si 3D está activo y hay moléculas
  if (speed) speed.style.display = (is3DEnabled && total > 0) ? 'flex' : 'none';

  if (!prevBtn || !nextBtn) return;

  if (total > 1) {
    prevBtn.style.display = i > 0         ? 'inline-block' : 'none';
    nextBtn.style.display = i < total - 1 ? 'inline-block' : 'none';
    prevBtn.disabled = (i <= 0);
    nextBtn.disabled = (i >= total - 1);
  } else {
    prevBtn.style.display = 'none';
    nextBtn.style.display = 'none';
  }
}

function downloadSingleXYZ(index) {
  const mol = molecules[index];
  if (!mol || !mol.xyz) {
    showError('XYZ no disponible para esta molécula.');
    return;
  }
  try {
    const formattedXYZ = formatXYZWithAlignment(mol.xyz);
    const blob = new Blob([formattedXYZ], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${safeFileName(mol.smiles)}.xyz`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error(e);
    showError('Error al descargar el archivo XYZ');
  }
}

async function downloadAllXYZ() {
  try {
    // ✅ Verificación robusta de JSZip
    if (typeof JSZip === 'undefined') {
      showError('⚠ No se encontró JSZip. Asegúrate de cargar la librería en index.html');
      return;
    }

    if (!molecules || molecules.length === 0) {
      showError('⚠ No hay moléculas convertidas.');
      return;
    }

    const zip = new JSZip();
    let anyAdded = false;

    molecules.forEach((mol, i) => {
      if (mol && mol.xyz) {
        const fname = `${String(i + 1).padStart(2, '0')}_${safeFileName(mol.smiles)}.xyz`;
        zip.file(fname, formatXYZWithAlignment(mol.xyz));
        anyAdded = true;
      }
    });

    if (!anyAdded) {
      showError('⚠ No hay archivos XYZ disponibles para empaquetar.');
      return;
    }

    // Generar ZIP y forzar descarga
    const blob = await zip.generateAsync({ type: 'blob' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = molecules.length > 1
      ? 'all_xyz.zip'
      : `${safeFileName(molecules[0].smiles)}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showSuccess('✔ ZIP con XYZ descargado');
  } catch (err) {
    console.error('Error en downloadAllXYZ:', err);
    showError('❌ Ocurrió un error al generar el ZIP de XYZ');
  }
}

function populateIndividualDownloads() {
  // Delegamos al único renderizador de botones para evitar duplicados
  updateDownloadButtons();
}

function updateDownloadButtons() {
  const box = document.getElementById('individual-downloads');
  if (!box) return;

  // Layout del contenedor (puedes mover esto a tu CSS)
  box.style.display = 'flex';
  box.style.flexDirection = 'column'; // uno debajo del otro
  box.style.gap = '10px';
  box.style.marginBottom = '14px';
  box.style.width = '100%';

  // Si no hay moléculas: limpiar y (opcional) mostrar botón legacy
  const hasMolecules = Array.isArray(molecules) && molecules.length > 0;
  if (!hasMolecules) {
    box.innerHTML = '';
    box.style.display = 'none';
    if (legacyDownloadBtn) legacyDownloadBtn.style.display = ''; // visible si NO hay simulación
    return;
  }

  // Hay moléculas -> ocultar botón legacy
  if (legacyDownloadBtn) legacyDownloadBtn.style.display = 'none';

  // Molécula visible
  const mol = molecules[currentMoleculeIndex];
  const label =
    mol?.alias || mol?.name || mol?.title || mol?.id || mol?.smiles || `mol_${currentMoleculeIndex + 1}`;

  // Render: SOLO 1 botón (visible) + 1 "All" si aplica
  box.innerHTML = '';

  // Botón: SMILES visible (AZUL, full width)
  const btnCurrent = document.createElement('button');
  btnCurrent.type = 'button';
  btnCurrent.className = 'btn btn-primary xyz-download';
  btnCurrent.textContent = `Download XYZ: ${String(label).slice(0, 32)}`;
  btnCurrent.style.width = '100%';
  btnCurrent.style.display = 'block';
  btnCurrent.addEventListener('click', () => downloadSingleXYZ(currentMoleculeIndex));
  box.appendChild(btnCurrent);

  // Botón: ALL (AZUL, full width)
  if (molecules.length > 1) {
    const btnAll = document.createElement('button');
    btnAll.type = 'button';
    btnAll.className = 'btn btn-primary xyz-download-all';
    btnAll.textContent = `Download all XYZ (${molecules.length})`;
    btnAll.style.width = '100%';
    btnAll.style.display = 'block';
    btnAll.style.marginLeft = '0'; // sin margen lateral
    btnAll.addEventListener('click', downloadAllXYZ);
    box.appendChild(btnAll);
  }

}

// === SMILES overflow UI (ancho completo + indicador + popover) ===
function initSmilesOverflowUI() {
  const input = document.getElementById('smiles');
  if (!input) return;

  // 🛡️ evita doble init (ya envuelto o ya existe el botón)
  if (input.parentElement && input.parentElement.classList.contains('smiles-wrap')) return;
  if (document.getElementById('smiles-indicator')) return;

  // 1) estilos una sola vez
  if (!document.getElementById('smiles-overflow-styles')) {
    const style = document.createElement('style');
    style.id = 'smiles-overflow-styles';
    style.textContent = `
      .smiles-wrap{ position:relative; display:flex; align-items:center; width:100%; }
      .smiles-wrap > input#smiles{
        flex:1 1 auto; min-width:0; width:100%;
        white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
        padding-right:2.2rem;
      }
      /* sin sombreado */
      .smiles-wrap.overflowing::after{
        content:""; position:absolute; right:2.0rem; top:0; bottom:0; width:2.5rem; pointer-events:none; background:none;
      }
      #smiles-indicator{
        position:absolute; right:6px; top:50%; transform:translateY(-50%);
        border:none; cursor:pointer; padding:.25rem .45rem; border-radius:8px;
        background:#2b2b4a; color:#fff; font-weight:700; line-height:1;
        opacity:0; pointer-events:none; transition:opacity .15s ease;
        z-index:2; /* ⬅️ que nunca quede debajo del input */
      }
      .smiles-wrap.overflowing #smiles-indicator{ opacity:1; pointer-events:auto; }

      #smiles-popover{
        position:absolute; z-index:2500; display:none;
        background:#12122B; border:1px solid #243149; border-radius:12px;
        box-shadow:0 12px 30px rgba(0,0,0,.45); padding:12px;
      }
      #smiles-popover.open{ display:block; }
      #smiles-popover .smiles-pop-content{ display:flex; flex-direction:column; gap:.75rem; }
      #smiles-popover pre{
        max-height:40vh; overflow:auto; margin:0; font-family:ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
        white-space:pre-wrap; word-break:break-all; color:#e8e8ff; background:#0e0f25; padding:10px; border-radius:8px;
      }
      #smiles-popover .smiles-actions{ display:flex; gap:.5rem; justify-content:flex-end; }
      #smiles-popover .smiles-actions button{ border:none; padding:.45rem .8rem; border-radius:10px; cursor:pointer; color:#fff; }
      #smiles-copy{ background:linear-gradient(135deg,#9D4EDD,#3CB49A); }
      #smiles-close{ background:#612020b0; }
    `;
    document.head.appendChild(style);
  }

  // 2) envolver y botón
  const wrap = document.createElement('div');
  wrap.className = 'smiles-wrap';
  input.parentNode.insertBefore(wrap, input);
  wrap.appendChild(input);

  const indicator = document.createElement('button');
  indicator.id = 'smiles-indicator';
  indicator.type = 'button';
  indicator.title = 'Show the full SMILES';
  indicator.setAttribute('aria-label', 'Show the full SMILES');
  indicator.textContent = '▾';
  wrap.appendChild(indicator);

  // 3) popover
  const pop = document.createElement('div');
  pop.id = 'smiles-popover';
  pop.innerHTML = `
    <div class="smiles-pop-content">
      <pre id="smiles-full"></pre>
      <div class="smiles-actions">
        <button id="smiles-copy">Copy</button>
        <button id="smiles-close">Close</button>
      </div>
    </div>`;
  document.body.appendChild(pop);

  const preFull = pop.querySelector('#smiles-full');
  const btnCopy = pop.querySelector('#smiles-copy');
  const btnClose = pop.querySelector('#smiles-close');

  // 4) overflow detector
  const checkOverflow = () => requestAnimationFrame(() => {
    wrap.classList.toggle('overflowing', input.scrollWidth > input.clientWidth);
  });
  input.addEventListener('input', checkOverflow);
  window.addEventListener('resize', checkOverflow);
  setTimeout(checkOverflow, 0);

  // 5) abrir popover
  indicator.addEventListener('click', () => {
    preFull.textContent = input.value || '';
    pop.classList.add('open');
    const r = wrap.getBoundingClientRect();
    pop.style.top = `${r.bottom + 8 + window.scrollY}px`;
    pop.style.left = `${r.left + window.scrollX}px`;
    pop.style.width = `${Math.max(r.width, 320)}px`;
  });

  // 6) cerrar/copiar
  btnClose.addEventListener('click', () => pop.classList.remove('open'));
  btnCopy.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(input.value || ''); showSuccess?.('✔ SMILES copied'); }
    catch(e) { console.warn(e); }
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') pop.classList.remove('open'); });
  document.addEventListener('click', (e) => {
    if (!pop.classList.contains('open')) return;
    if (!pop.contains(e.target) && !wrap.contains(e.target)) pop.classList.remove('open');
  });
}

// Llama a la inicialización cuando el DOM esté listo (si aún no lo haces)
document.addEventListener('DOMContentLoaded', () => {
  try { initSmilesOverflowUI(); } catch (e) { console.warn(e); }
});


window.retryVisualization = retryVisualization;
window.navigateMolecules = navigateMolecules;
window.toggleRotation = toggleRotation;
window.changeRotationSpeed = changeRotationSpeed;
