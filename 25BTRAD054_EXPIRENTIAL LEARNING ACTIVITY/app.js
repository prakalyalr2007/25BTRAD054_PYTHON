/**
 * Campus Canteen Ordering System - Frontend Client Scripts
 * Handles Dark Mode, Live Status Polling, Staff Queue Sync, Modals, and Alerts.
 */

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initMobileNav();
  initAlertDismissal();
  initLiveOrderTracker();
  initStaffQueueAutoRefresh();
  initModalHandlers();
});

/* ==========================================================================
   1. Theme Management (System preference + Manual LocalStorage Toggle)
   ========================================================================== */
function initTheme() {
  const toggleBtn = document.getElementById('theme-toggle-btn');
  const storedTheme = localStorage.getItem('canteen_theme');

  if (storedTheme) {
    document.documentElement.setAttribute('data-theme', storedTheme);
    updateThemeIcon(storedTheme);
  } else {
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initialTheme = prefersDark ? 'dark' : 'light';
    updateThemeIcon(initialTheme);
  }

  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const currentTheme = document.documentElement.getAttribute('data-theme') || 
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      
      const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', newTheme);
      localStorage.setItem('canteen_theme', newTheme);
      updateThemeIcon(newTheme);
    });
  }
}

function updateThemeIcon(theme) {
  const toggleBtn = document.getElementById('theme-toggle-btn');
  if (toggleBtn) {
    toggleBtn.innerHTML = theme === 'dark' ? '☀️' : '🌙';
    toggleBtn.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`);
  }
}

/* ==========================================================================
   2. Mobile Navigation Toggle
   ========================================================================== */
function initMobileNav() {
  const toggle = document.querySelector('.mobile-nav-toggle');
  const menu = document.querySelector('.nav-menu');

  if (toggle && menu) {
    toggle.addEventListener('click', () => {
      menu.classList.toggle('open');
      const isOpen = menu.classList.contains('open');
      toggle.setAttribute('aria-expanded', isOpen);
    });
  }
}

/* ==========================================================================
   3. Alert Auto-Dismissal
   ========================================================================== */
function initAlertDismissal() {
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(alert => {
    // Add close button if not present
    if (!alert.querySelector('.alert-close-btn')) {
      const closeBtn = document.createElement('button');
      closeBtn.className = 'alert-close-btn';
      closeBtn.innerHTML = '&times;';
      closeBtn.setAttribute('aria-label', 'Close alert');
      closeBtn.onclick = () => alert.remove();
      alert.appendChild(closeBtn);
    }

    // Auto dismiss after 6 seconds
    setTimeout(() => {
      alert.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
      alert.style.opacity = '0';
      alert.style.transform = 'translateY(-10px)';
      setTimeout(() => alert.remove(), 300);
    }, 6000);
  });
}

/* ==========================================================================
   4. Live Order Status Tracker (Automatic Polling without Refresh)
   ========================================================================== */
function initLiveOrderTracker() {
  const tracker = document.getElementById('live-order-tracker');
  if (!tracker) return;

  const orderId = tracker.dataset.orderId;
  let currentStatus = tracker.dataset.status;

  // Don't poll if order is already terminal (Collected or Cancelled)
  if (['Collected', 'Cancelled'].includes(currentStatus)) {
    return;
  }

  const pollInterval = setInterval(async () => {
    try {
      const response = await fetch(`/api/order/${orderId}/status`);
      if (!response.ok) return;

      const data = await response.json();
      if (data.status && data.status !== currentStatus) {
        currentStatus = data.status;
        tracker.dataset.status = currentStatus;
        updateOrderUI(data);

        if (['Collected', 'Cancelled'].includes(currentStatus)) {
          clearInterval(pollInterval);
        }
      }
    } catch (e) {
      console.warn('Live order status poll failed, will retry...', e);
    }
  }, 4000);
}

function updateOrderUI(data) {
  // Update Status Pill
  const statusPills = document.querySelectorAll('.status-pill-target');
  statusPills.forEach(pill => {
    pill.className = `status-pill status-pill-target ${data.status}`;
    pill.innerHTML = `<span class="pulse-dot"></span> ${data.status}`;
  });

  // Update Stepper Progress
  const stages = ['Received', 'Preparing', 'Ready', 'Collected'];
  const currentIdx = stages.indexOf(data.status);

  const steps = document.querySelectorAll('.timeline-step');
  steps.forEach((step, idx) => {
    const stepStage = step.dataset.stage;
    step.classList.remove('active', 'completed');

    if (data.status === 'Cancelled') {
      step.classList.remove('active', 'completed');
    } else if (idx < currentIdx) {
      step.classList.add('completed');
    } else if (idx === currentIdx) {
      step.classList.add('active');
    }
  });

  const progressLine = document.querySelector('.timeline-progress');
  if (progressLine) {
    if (data.status === 'Cancelled') {
      progressLine.style.width = '0%';
    } else {
      const pct = (currentIdx / (stages.length - 1)) * 100;
      progressLine.style.width = `${pct}%`;
    }
  }

  // Hide Cancel button if moved past Received
  const cancelSection = document.getElementById('cancel-order-container');
  if (cancelSection && !data.can_cancel) {
    cancelSection.style.display = 'none';
  }
}

/* ==========================================================================
   5. Staff Queue Auto-Refresh
   ========================================================================== */
function initStaffQueueAutoRefresh() {
  const queueContainer = document.getElementById('staff-queue-container');
  if (!queueContainer) return;

  let lastOrderIds = queueContainer.dataset.orderIds || '';

  setInterval(async () => {
    try {
      const response = await fetch('/api/staff/queue-data');
      if (!response.ok) return;

      const orders = await response.json();
      const currentIds = orders.map(o => `${o.id}:${o.status}`).join(',');

      // If queue changed, reload to sync status and action buttons cleanly
      if (lastOrderIds !== '' && currentIds !== lastOrderIds) {
        lastOrderIds = currentIds;
        window.location.reload();
      } else {
        lastOrderIds = currentIds;
      }
    } catch (e) {
      console.warn('Queue auto-refresh check error:', e);
    }
  }, 5000);
}

/* ==========================================================================
   6. Modal Handlers (Admin Add/Edit Menu Items)
   ========================================================================== */
function initModalHandlers() {
  // Open add modal
  const openAddBtn = document.getElementById('open-add-item-modal');
  const addModal = document.getElementById('add-item-modal');
  if (openAddBtn && addModal) {
    openAddBtn.addEventListener('click', () => {
      addModal.classList.add('open');
    });
  }

  // Edit buttons
  const editButtons = document.querySelectorAll('.edit-item-btn');
  const editModal = document.getElementById('edit-item-modal');
  const editForm = document.getElementById('edit-item-form');

  if (editButtons.length > 0 && editModal && editForm) {
    editButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.dataset.id;
        const name = btn.dataset.name;
        const category = btn.dataset.category;
        const price = btn.dataset.price;
        const isVeg = btn.dataset.isVeg === '1';
        const isAvailable = btn.dataset.isAvailable === '1';
        const description = btn.dataset.description;
        const emoji = btn.dataset.emoji;

        editForm.action = `/admin/menu/${id}/edit`;
        document.getElementById('edit-name').value = name;
        document.getElementById('edit-category').value = category;
        document.getElementById('edit-price').value = price;
        document.getElementById('edit-veg').checked = isVeg;
        document.getElementById('edit-available').checked = isAvailable;
        document.getElementById('edit-description').value = description;
        document.getElementById('edit-emoji').value = emoji;

        editModal.classList.add('open');
      });
    });
  }

  // Close modals on clicking close buttons or backdrop
  const closeButtons = document.querySelectorAll('.modal-close-btn, .modal-cancel-btn');
  closeButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.modal-backdrop').forEach(m => m.classList.remove('open'));
    });
  });

  document.querySelectorAll('.modal-backdrop').forEach(modal => {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) {
        modal.classList.remove('open');
      }
    });
  });
}
