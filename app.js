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

    // Inicializar opciones de campo de fuerza
    try {
        toggleForceField();
    } catch (e) {
        console.warn("⚠ Error en toggleForceField:", e);
    }

    // Autocarga de la molécula de oxitocina
    const smilesInput = document.getElementById('smiles');
    if (smilesInput && !sessionStorage.getItem('oxytocinShown')) {
        const oxytocinSmiles = "CC(C)C[C@H](NC(=O)[C@H](CC(C)C)NC(=O)CN)C(=O)N";
        smilesInput.value = oxytocinSmiles;
        molecules = [{ smiles: oxytocinSmiles, id: oxytocinSmiles }];
        updateSmilesHistory(oxytocinSmiles);

        convertSingleMolecule().catch(err => {
            console.error("❌ Error al convertir oxitocina automáticamente:", err);
        });

        sessionStorage.setItem('oxytocinShown', 'true');
    }

    // Conexión al backend
    try {
        checkBackendConnection();
    } catch (e) {
        console.warn("⚠️ Error en checkBackendConnection:", e);
    }

    // Historial y botón de conversión
    try {
        loadSmilesHistory();
        setupConversionHandler();
    } catch (e) {
        console.warn("⚠️ Error cargando historial o handler de conversión:", e);
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

    // Navegación: Home
    const homeLink = document.querySelector('a[href="#home"]');
    const homeSection = document.getElementById('home-info');
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

    if (homeLink) {
        homeLink.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelectorAll('main > section').forEach(section => section.style.display = 'none');
            if (homeSection) {
                homeSection.style.display = 'block';
                setTimeout(() => {
                    window.scrollTo({ top: homeSection.offsetTop - 40, behavior: 'smooth' });
                }, 100);
            }
            if (header) header.style.display = 'none';
        });
    }

    // Navegación: Simulator
    const simulatorLink = document.querySelector('a[href="#simulator"]');
    if (simulatorLink) {
        simulatorLink.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelectorAll('main > section').forEach(section => section.style.display = 'none');
            if (inputSection) inputSection.style.display = 'block';
            if (conversionSection) conversionSection.style.display = 'flex';
            if (header) header.style.display = 'block';
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // Navegación: Background
    const backgroundLink = document.querySelector('a[href="#background"]');
    const backgroundSection = document.getElementById('background-info');

    if (backgroundLink) {
        backgroundLink.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelectorAll('main > section').forEach(section => section.style.display = 'none');
            if (backgroundSection) {
                backgroundSection.style.display = 'block';
                setTimeout(() => {
                    window.scrollTo({ top: backgroundSection.offsetTop - 40, behavior: 'smooth' });
                }, 100);
            }
            if (header) header.style.display = 'none';
        });
    }

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

            // Limpia modal viejo si quedó alguno
            document.getElementById('molecule-selection-modal')?.remove();

            // Abre modal selección múltiple
            const selectedSet = await showMoleculeSelectionModal(window.allMolecules);
            if (selectedSet && selectedSet.size) {
                const pickedIdx = [...selectedSet].map(Number).filter(i => i >= 0 && i < window.allMolecules.length).sort((a,b)=>a-b);
                const picked    = pickedIdx.map(i => window.allMolecules[i]);

                window.molecules = picked;
                window.currentMoleculeIndex = 0;

                const smilesInput = document.getElementById('smiles');
                if (smilesInput) smilesInput.value = '';

            await convertMolecules(picked);   // <- importante pasar picked
            } else {
            showError("No molecules selected.");
            }

        } else {
            showError("Please select an input method.");
        }
        } catch (error) {
        console.error(error);
        showError(error?.message || "Conversion failed.");
        }
    });
    }

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

        const parsed = [];
        text.split('\n').forEach((line) => {
            const trimmed = line.trim();
            if (!trimmed) return;
            if (/^#|^\/\//.test(trimmed)) return;

            const parts  = trimmed.split(/\s+/);
            const smiles = parts[0]?.trim();
            const id     = (parts.length >= 2 ? parts[1] : `mol_${parsed.length + 1}`)?.trim();
            if (smiles) parsed.push({ smiles, id });
        });

        if (parsed.length === 0) throw new Error("Archivo vacío o inválido");

        // Reset de estado global
        window.allMolecules = parsed.slice();
        window.molecules    = parsed.slice();
        window.currentMoleculeIndex = 0;
        window.selected?.clear?.();

        const loadConfirmation = document.getElementById('load-confirmation');
        if (loadConfirmation && window.showConfirmation) {
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
        showError(`Error al cargar SMILES: ${error.message}`);
        }
    });
    }
});

document.querySelectorAll('#smiles-examples span').forEach(span => {
    span.addEventListener('click', () => {
        const smiles = span.getAttribute('data-smiles');
        const smilesInput = document.getElementById('smiles');
        if (smilesInput) {
            smilesInput.value = smiles;
            smilesInput.classList.add('touched');
        }
    });
});

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
        downloadXYZ(); // Esta función ya usa currentXYZ y currentMoleculeIndex
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

    // Nuevos event listeners
if (prevMoleculeBtn) prevMoleculeBtn.addEventListener('click', () => navigateMolecules(-1));
if (nextMoleculeBtn) nextMoleculeBtn.addEventListener('click', () => navigateMolecules(1));
if (rotationSpeedInput) rotationSpeedInput.addEventListener('input', (e) => changeRotationSpeed(e.target.value));

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

        /* Cargar por defecto la oxitocina al iniciar
    if (!molecules.length) {
        const oxytocinSmiles = "CC(C)C[C@H](NC(=O)[C@H](CC(=O)N[C@@H](CCCNC(=N)N)C(=O)N[C@H](CSSC[C@H](C(=O)N[C@H](C)C(=O)N[C@H](CCC(=O)O)C(=O)N[C@H](CO)C(=O)N1CCC[C@H]1C(=O)N[C@H](CCCCN)C(=O)N2CCCC2)NC(=O)[C@H](Cc1ccc(O)cc1)NC(=O)[C@H](N)C(C)C)NC(=O)[C@H](N)CO)NC(=O)[C@H](N)CC(=O)O)C(=O)O";
        document.getElementById('smiles').value = oxytocinSmiles;
        molecules = [{ smiles: oxytocinSmiles, id: "Oxitocina" }];
        updateSmilesHistory(oxytocinSmiles);  // opcional si quieres agregarla al historial
        convertSingleMolecule(); // Lanza la conversión automática
        }*/

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
    recordBtn.title = recording ? "Stop Recording" : "Start Recording";
}

function countdown(seconds, callback) {
    countdownEl.style.display = 'block';
    let current = seconds;
    const timer = setInterval(() => {
        countdownEl.textContent = current;
        current--;
        if (current < 0) {
            clearInterval(timer);
            countdownEl.style.display = 'none';
            callback();
        }
    }, 1000);
}

let timerInterval;
let startTime;

function startRecording() {
    const canvas = document.querySelector('#viewer-container canvas');
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
        document.getElementById('countdown').style.display = 'none';

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
    const countdownEl = document.getElementById('countdown');
    countdownEl.style.display = 'block';
    timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        countdownEl.textContent = formatTime(elapsed);
    }, 1000);
}

function formatTime(seconds) {
    const mins = Math.floor(seconds / 60).toString().padStart(2, '0');
    const secs = (seconds % 60).toString().padStart(2, '0');
    return `${mins}:${secs}`;
}


function stopRecording() {
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

function toggleView(mode) {
  if (mode === "3d") {
    // Cambia el estado de 3D (permite activar/desactivar)
    is3DEnabled = !is3DEnabled;
  } else if (mode === "2d") {
    // Cambia el estado de 2D (permite activar/desactivar)
    is2DEnabled = !is2DEnabled;
  }

  // Asegura que al menos uno esté activo
  if (!is3DEnabled && !is2DEnabled) {
    if (mode === "3d") {
      is2DEnabled = true;
    } else {
      is3DEnabled = true;
    }
  }

  // Actualiza estilos de botones
  if (is3DEnabled) btn3D.classList.add("active");
  else btn3D.classList.remove("active");

  if (is2DEnabled) btn2D.classList.add("active");
  else btn2D.classList.remove("active");

  // Si ambos están activos, mostrar vista combinada
  // Si solo uno, mostrar su modo completo
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
        btn2D.classList.add("active");
        btn3D.classList.remove("active");

        // Actualizar visualización
        updateViewerContainerLayout();
    });
});

// Funciones principales
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
            showSuccess('<strong>✔ Connection established.</strong> Ready for use.');
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
        molBlock: molBlock || null
      });

      showSuccess(`<strong>✔ Molecule successfully converted</strong><br><strong>SMILES:</strong> ${mol.smiles}`);
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
    const format    = hasXYZ ? 'xyz' : (hasMol ? 'sdf' : 'xyz');
    const modelData = hasXYZ ? currentMol.xyz : (hasMol ? currentMol.molBlock : '');

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
  try {
    if (!Array.isArray(molecules) || molecules.length === 0 || !molecules[currentMoleculeIndex]) {
      const smilesInput = document.getElementById('smiles');
      const smilesText  = smilesInput?.value?.trim();
      if (!smilesText) throw new Error('No molecule selected. Please enter a SMILES string.');
      molecules = [{ smiles: smilesText, id: smilesText }];
      currentMoleculeIndex = 0;
    }

    const method     = document.getElementById('conversion-method')?.value || 'rdkit';
    const forceField = document.getElementById('force-field')?.value || 'UFF';
    const molecule   = molecules[currentMoleculeIndex];

    const response = await fetch(`${API_BASE_URL}/convert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ smiles: molecule.smiles, identifier: molecule.id, method, force_field: forceField })
    });

    if (!response.ok) {
      let serverErr = 'Error en la conversión';
      try { const e = await response.json(); if (e?.error) serverErr = e.error; } catch {}
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
    updateXYZDisplay?.();
    const xyzDisplay = document.getElementById('xyz-display');
    if (xyzDisplay) xyzDisplay.style.display = 'block';

    const molText =
      (typeof data?.mol === 'string' && data.mol) ? data.mol :
      (data?.mol && typeof data.mol.mol === 'string' ? data.mol.mol : '');

    molecules[currentMoleculeIndex] = {
      ...molecules[currentMoleculeIndex],
      xyz: xyzWithHeader,
      molBlock: molText || null
    };

    updateViewerContainerLayout();

    showSuccess?.(`<strong>✔ Molecule successfully converted</strong><br><strong>SMILES:</strong> ${molecule.smiles}`);

    // ✅ Asegurar visibilidad de controles y slider en single
    const moleculeCtrls = document.getElementById('molecule-controls');
    const speedControl  = document.querySelector('.speed-control');
    if (moleculeCtrls) moleculeCtrls.style.display = 'flex';
    if (speedControl)  speedControl.style.display  = is3DEnabled ? 'flex' : 'none';

    updateDownloadButtons?.();
    updateNavigationButtons?.();
    updateDownloadButtons();

    // === Forzar visibilidad del deslizador de velocidad (sin redeclarar) ===
    const speedControlEl = document.querySelector('.speed-control');
    if (speedControlEl) {
      speedControlEl.style.display = 'flex';
      const rotationInput = document.getElementById('rotation-speed');
      if (rotationInput) {
        rotationInput.min = 0;
        rotationInput.max = 5;
        rotationInput.step = 0.5;
        rotationInput.value = rotationSpeed;
      }
    }
  } catch (err) {
    console.error(err);
    showError?.(err?.message || 'Unexpected error during conversion');
  }
}

function updateXYZDisplay() {
    const xyzDisplay = document.getElementById('xyz-display');
    if (xyzDisplay) {
        const lines = currentXYZ.trim().split('\n');
        xyzDisplay.style.display = 'block';
        if (lines.length >= 3) {
            const header = lines.slice(0, 2);
            const atoms = lines.slice(2).map(line => {
                const parts = line.trim().split(/\s+/);
                return parts.length === 4
                ? `${parts[0].padEnd(2)} ${parts[1].padStart(8)} ${parts[2].padStart(8)} ${parts[3].padStart(8)}`
                : line;
            });
            xyzDisplay.textContent = [...header, ...atoms].join('\n');
        } else {
            xyzDisplay.textContent = currentXYZ; // fallback
        }
        xyzDisplay.style.display = 'block';
    }
}

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

    // Crear viewer en el contenedor indicado
    const viewer = $3Dmol.createViewer(targetContainer, {
        width: targetContainer.offsetWidth || 500,
        height: targetContainer.offsetHeight || 400,
        backgroundColor: 'black'
    });

    try {
        viewer.addModel(modelData, format, {
            keepH: true,
            noComputeSecondaryStructure: true
        });

        viewer.setStyle({}, {
            stick: { radius: 0.15 },
            sphere: { scale: 0.25 }
        });

        viewer.zoomTo();
        viewer.zoom(1);
        viewer.render();
    } catch (e) {
        console.error("❌ Error al renderizar modelo:", e);
        targetContainer.innerHTML = `<div class="placeholder error">Error al renderizar molécula</div>`;
        return;
    }

    // Animación de rotación
    const animate = () => {
        if (!isRotationPaused) {
            viewer.rotate(rotationSpeed, { x: 0, y: 1, z: 0 });
            viewer.render();
        }
        rotationAnimationId = requestAnimationFrame(animate);
    };
    animate();

    // Guardar instancia actual
    currentVisualizations = [viewer];

    // Ocultar placeholder si está presente
    const placeholder = document.querySelector('.placeholder');
    if (placeholder) placeholder.style.display = 'none';

    // Redibujar con retardo para asegurar dimensiones
    setTimeout(() => {
        try {
            viewer.resize();
            viewer.zoomTo(1.2);
            viewer.render();
        } catch (err) {
            console.warn("⚠ Error al redibujar viewer:", err);
        }
    }, 100);
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

function downloadImage() {
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

function updateLoadConfirmation() {
    if (!loadConfirmation) {
        loadConfirmation = document.getElementById('load-confirmation');
    }

    if (loadConfirmation) {
        const moleculeInfo = molecules.map(mol => 
            `<div><strong>SMILES:</strong> ${mol.smiles}</div><div><strong>ID:</strong> ${mol.id}</div>`
        ).join('<hr>');
        
        loadConfirmation.innerHTML = `
            <div class="alert success">
                ${molecules.length === 1 ? 'Molécula cargada exitosamente:' : `${molecules.length} moléculas cargadas exitosamente:`}
                ${moleculeInfo}
            </div>
        `;
        loadConfirmation.style.display = 'block';
        setTimeout(() => {
            loadConfirmation.style.display = 'none';
        }, 5000);
    }
}

function enableConversionControls() {
    const convertBtn = document.getElementById('convert-molecules');
    const mol1Select = document.getElementById('mol1');
    const mol2Select = document.getElementById('mol2');
    const compareMolSelect = document.getElementById('compare-molecule');

    if (convertBtn) convertBtn.disabled = false;
    
    if (mol1Select && mol2Select && compareMolSelect) {
        // Limpiar y llenar selects
        mol1Select.innerHTML = '';
        mol2Select.innerHTML = '';
        compareMolSelect.innerHTML = '';
        
        molecules.forEach(mol => {
            const option = document.createElement('option');
            option.value = mol.id;
            option.textContent = `${mol.id} (${mol.smiles})`;
            
            mol1Select.appendChild(option.cloneNode(true));
            mol2Select.appendChild(option.cloneNode(true));
            compareMolSelect.appendChild(option);
        });
        
        mol1Select.disabled = false;
        mol2Select.disabled = false;
        compareMolSelect.disabled = false;
        document.getElementById('calculate-similarity').disabled = false;
        document.getElementById('compare-methods').disabled = false;
    }
}

function toggleForceField() {
    const method = document.getElementById('conversion-method')?.value;
    const forceFieldDiv = document.getElementById('force-field-options');

    if (!method || !forceFieldDiv) {
        console.warn("Elementos necesarios para toggleForceField no están disponibles aún.");
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

    const header = lines.slice(0, 2);
    const atomLines = lines.slice(2).map(line => {
        const parts = line.trim().split(/\s+/);
        return parts.length === 4
            ? `${parts[0].padEnd(2)} ${parts[1].padStart(8)} ${parts[2].padStart(8)} ${parts[3].padStart(8)}`
            : line;
    });

    return [...header, ...atomLines].join('\n');
}

// Funciones de ayuda
function showSuccess(message) {
    console.log("Mostrando mensaje de éxito:", message);
    const alertDiv = document.createElement('div');
    alertDiv.className = 'alert success';
    alertDiv.innerHTML = message;
    document.body.appendChild(alertDiv);
    setTimeout(() => {
        alertDiv.remove();
    }, 3000);
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
    document.body.appendChild(alertDiv);
    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
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
    let history = JSON.parse(localStorage.getItem(key)) || [];

    // Elimina duplicados y agrega nuevo al principio
    history = [newSmiles, ...history.filter(s => s !== newSmiles)];

    // Limita a 5 entradas
    history = history.slice(0, 5);

    // Guarda en localStorage
    localStorage.setItem(key, JSON.stringify(history));

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
    const history = JSON.parse(localStorage.getItem(key)) || [];
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

function setupConversionHandler() {
  // Legacy / no-op: el listener correcto ya está definido arriba.
}

function showLoader(show) {
    const loader = document.querySelector('.water-loader');
    if (loader) {
        loader.style.display = show ? 'block' : 'none';
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

window.retryVisualization = retryVisualization;
window.navigateMolecules = navigateMolecules;
window.toggleRotation = toggleRotation;
window.changeRotationSpeed = changeRotationSpeed;
window.navigateMolecules = navigateMolecules;
window.toggleRotation = toggleRotation;
window.changeRotationSpeed = changeRotationSpeed;
window.retryVisualization = retryVisualization;
