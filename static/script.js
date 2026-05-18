// ── Toast Notification ─────────────────────────────────────
// Usage: showToast('Attendance saved!', 'success')
// Types: 'success', 'error', 'info'
function showToast(message, type = 'info', duration = 3000) {
    // Remove existing toast if any
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transition = 'opacity 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

// ── Format Time ────────────────────────────────────────────
// Converts 24hr time string to 12hr format
// Usage: formatTime('14:30:00') → '2:30 PM'
function formatTime(timeStr) {
    const [hour, minute] = timeStr.split(':');
    const h = parseInt(hour);
    const suffix = h >= 12 ? 'PM' : 'AM';
    const h12 = h % 12 || 12;
    return `${h12}:${minute} ${suffix}`;
}

// ── Format Date ────────────────────────────────────────────
// Converts YYYY-MM-DD to readable format
// Usage: formatDate('2025-03-25') → 'March 25, 2025'
function formatDate(dateStr) {
    const date = new Date(dateStr + 'T00:00:00');
    return date.toLocaleDateString('en-US', {
        year: 'numeric', month: 'long', day: 'numeric'
    });
}

// ── Get Today's Date ───────────────────────────────────────
// Returns today in YYYY-MM-DD format for input[type=date]
function todayDate() {
    return new Date().toISOString().slice(0, 10);
}

// ── Confirm Dialog ─────────────────────────────────────────
// Simple async confirm wrapper
// Usage: const ok = await confirmDialog('Are you sure?')
function confirmDialog(message) {
    return new Promise(resolve => {
        resolve(window.confirm(message));
    });
}