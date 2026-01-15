const socket = io();

// === Authentication State ===
let isAuthenticated = false;
const pinScreen = document.getElementById('pinScreen');
const pinInput = document.getElementById('pinInput');
const pinSubmit = document.getElementById('pinSubmit');
const pinError = document.getElementById('pinError');
const connectedStatus = document.getElementById('connectedStatus');

// === Touchpad State ===
let scrollCooldownUntil = 0;
let lastTouchX = null;
let lastTouchY = null;
let hasMoved = false;

let lastTapTime = 0;
let isDragging = false;

let lastTwoFingerTime = 0;
let lastTwoFingerMoved = false;
let twoFingerScrollStartTime = 0;

let activeTouchCount = 0;
let pendingRightClick = false;
let rightClickTimer = null;

const MONITOR_WIDTH = 1920;
const MONITOR_HEIGHT = 1080;
const PHONE_WIDTH = window.innerWidth;
const PHONE_HEIGHT = window.innerHeight;

const SCALE_X = (MONITOR_WIDTH / PHONE_WIDTH) * 0.8;
const SCALE_Y = (MONITOR_HEIGHT / PHONE_HEIGHT) * 1.2;
const keyboardInput = document.getElementById('keyboardInput');
const display = document.getElementById('display');

// === Socket Events ===
socket.on('connect', () => {
  console.log('[WEB] Connected to server');
});

socket.on('auth_status', (data) => {
  console.log('[WEB] Auth status:', data);
  if (data.trusted) {
    isAuthenticated = true;
    pinScreen.classList.add('hidden');
    showConnectedStatus();
    if (data.message) {
      pinError.style.color = '#28a745';
      pinError.textContent = data.message;
    }
  } else {
    isAuthenticated = false;
    pinScreen.classList.remove('hidden');
    if (data.message) {
      pinError.style.color = '#ff4444';
      pinError.textContent = data.message;
    }
  }
});

function showConnectedStatus() {
  connectedStatus.classList.add('show');
  setTimeout(() => {
    connectedStatus.classList.remove('show');
  }, 2000);
}

// === PIN Entry ===
pinSubmit.addEventListener('click', submitPin);
pinInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    submitPin();
  }
});

function submitPin() {
  const pin = pinInput.value.trim();
  if (pin.length === 4) {
    pinError.textContent = '';
    socket.emit('check_pin', pin);
  } else {
    pinError.textContent = 'Please enter a 4-digit PIN';
  }
}

// === Touch Handlers ===
function handleTouchStart(e) {
  if (!isAuthenticated) return;

  activeTouchCount = e.touches.length;

  if (e.touches.length === 2) {
    pendingRightClick = true;
    lastTwoFingerMoved = false;
    rightClickTimer = setTimeout(() => {
      pendingRightClick = false;
    }, 400);
    lastTwoFingerTime = Date.now();
    twoFingerScrollStartTime = Date.now();
    return;
  }

  if (e.touches.length !== 1) return;

  const now = Date.now();
  const delta = now - lastTapTime;
  lastTapTime = now;

  const touch = e.touches[0];
  lastTouchX = touch.clientX;
  lastTouchY = touch.clientY;
  hasMoved = false;

  if (delta < 300) {
    isDragging = true;
    socket.emit('mousedown');
    console.log('[WEB] Drag mode: mouseDown');
  }
}

function handleTouchMove(e) {
  if (!isAuthenticated) return;

  if (e.touches.length === 2) {
    const t1 = e.touches[0];
    const t2 = e.touches[1];
    const avgX = (t1.clientX + t2.clientX) / 2;
    const avgY = (t1.clientY + t2.clientY) / 2;

    const dx = avgX - lastTouchX;
    const dy = avgY - lastTouchY;

    if (Math.abs(dx) > 2 || Math.abs(dy) > 2) {
      socket.emit('scroll', { dx: Math.sign(dx), dy: Math.sign(dy) });
      lastTwoFingerMoved = true;
    }

    scrollCooldownUntil = Date.now() + 300;
    lastTouchX = avgX;
    lastTouchY = avgY;
    lastTwoFingerTime = Date.now();
    return;
  }

  if (Date.now() < scrollCooldownUntil) return;
  if (e.touches.length !== 1) return;

  const touch = e.touches[0];
  const newX = touch.clientX;
  const newY = touch.clientY;

  const rawDx = newX - lastTouchX;
  const rawDy = newY - lastTouchY;

  if (Math.abs(rawDx) > 100 || Math.abs(rawDy) > 100) {
    lastTouchX = newX;
    lastTouchY = newY;
    return;
  }

  const dx = rawDx * SCALE_X;
  const dy = rawDy * SCALE_Y;

  if (Math.abs(dx) > 1 || Math.abs(dy) > 1) {
    socket.emit('move', { dx, dy });
    hasMoved = true;
  }

  lastTouchX = newX;
  lastTouchY = newY;
}

function handleTouchEnd(e) {
  if (!isAuthenticated) return;

  const now = Date.now();
  activeTouchCount = e.touches.length;
  const isTwoFingerEnd = e.changedTouches.length === 2;

  // === Right Click ===
  if (pendingRightClick && isTwoFingerEnd && activeTouchCount === 0) {
    clearTimeout(rightClickTimer);
    pendingRightClick = false;
    if (!lastTwoFingerMoved) {
      socket.emit('rightclick');
      console.log('[WEB] Right click via two-finger tap');
    }
    return;
  }

  // === Drag End ===
  if (isDragging) {
    socket.emit('mouseup');
    console.log('[WEB] Drag mode: mouseUp');
    isDragging = false;
    return;
  }

  if (now < scrollCooldownUntil) return;

  // === Left Click ===
  if (!hasMoved) {
    socket.emit('click');
  }
}


// === Keyboard Input ===
let backspaceHoldInterval = null;
let currentText = '';
let ignoreInput = false;

keyboardInput.addEventListener('keydown', (e) => {
  if (!isAuthenticated) return;

  if (e.key === 'Backspace') {
    ignoreInput = true;
    if (!backspaceHoldInterval) {
      socket.emit('type', 'BACKSPACE');
      if (display) display.textContent = currentText;
      backspaceHoldInterval = setInterval(() => {
        socket.emit('type', 'BACKSPACE');
        if (display) display.textContent = currentText;
      }, 100);
    }
    e.preventDefault();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    ignoreInput = true;
    keyboardInput.value = '';
    socket.emit('type', 'ENTER');
  }
});

keyboardInput.addEventListener('keyup', (e) => {
  if (e.key === 'Backspace') {
    ignoreInput = false;
    clearInterval(backspaceHoldInterval);
    backspaceHoldInterval = null;
    e.preventDefault();
  } else if (e.key === 'Enter') {
    e.preventDefault();
    ignoreInput = false;
  }
});

keyboardInput.addEventListener('input', (e) => {
  if (!isAuthenticated) return;

  const val = e.target.value;

  if (ignoreInput) {
    return;
  }

  if (val.length > 0) {
    const char = val[val.length - 1];
    currentText += char;
    socket.emit('type', char);
    if (display) display.textContent = currentText;
    keyboardInput.value = '';
  }
});


// === Initialize ===
window.addEventListener('load', () => {
  document.body.addEventListener('touchstart', handleTouchStart, { passive: false });
  document.body.addEventListener('touchmove', handleTouchMove, { passive: false });
  document.body.addEventListener('touchend', handleTouchEnd);
});
