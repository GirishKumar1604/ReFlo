/* ═══════════════════════════════════════════
   Dashboard — Interactive Logic
   Controls the agent console, prompt tabs,
   sheet tabs, patch drawer, and simulated workflow.
   ═══════════════════════════════════════════ */

(function () {
  'use strict';

  // ─── Theme toggle ───
  function initThemeToggle() {
    const btn = document.getElementById('themeToggle');
    if (!btn) return;

    const saved = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const initial = saved || (prefersDark ? 'dark' : 'light');

    if (initial === 'dark') {
      document.documentElement.setAttribute('data-theme', 'dark');
    }

    btn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme');
      const next = current === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      localStorage.setItem('theme', next);
      showToast(next === 'dark' ? 'Dark mode enabled' : 'Light mode enabled');
    });
  }

  // ─── Toast ───
  function showToast(message) {
    const toast = document.getElementById('toast');
    const msg = document.getElementById('toastMessage');
    if (!toast || !msg) return;

    msg.textContent = message;
    if (toast._hideTimeout) clearTimeout(toast._hideTimeout);

    requestAnimationFrame(() => {
      toast.classList.add('show');
      toast._hideTimeout = setTimeout(() => {
        toast.classList.remove('show');
      }, 2500);
    });
  }

  // ─── Scroll-aware nav ───
  function initScrollNav() {
    const nav = document.getElementById('mainNav');
    if (!nav) return;

    let ticking = false;
    window.addEventListener('scroll', () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          nav.classList.toggle('scrolled', window.scrollY > 20);
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
  }

  // ─── Prompt tabs ───
  function initPromptTabs() {
    const taskBtn = document.getElementById('taskPromptTabBtn');
    const bizBtn = document.getElementById('businessPromptTabBtn');
    const taskView = document.getElementById('taskPromptView');
    const bizView = document.getElementById('businessPromptView');

    if (!taskBtn || !bizBtn || !taskView || !bizView) return;

    taskBtn.addEventListener('click', () => {
      taskBtn.classList.add('active');
      taskBtn.setAttribute('aria-selected', 'true');
      bizBtn.classList.remove('active');
      bizBtn.setAttribute('aria-selected', 'false');
      taskView.classList.add('active');
      bizView.classList.remove('active');
    });

    bizBtn.addEventListener('click', () => {
      bizBtn.classList.add('active');
      bizBtn.setAttribute('aria-selected', 'true');
      taskBtn.classList.remove('active');
      taskBtn.setAttribute('aria-selected', 'false');
      bizView.classList.add('active');
      taskView.classList.remove('active');
    });
  }

  // ─── Patch Drawer ───
  function initDrawer() {
    const overlay = document.getElementById('patchDrawerOverlay');
    const openBtn = document.getElementById('openPatchDrawer');
    const closeBtn = document.getElementById('closePatchDrawer');
    if (!overlay || !openBtn) return;

    function openDrawer() {
      overlay.classList.add('open');
      document.body.style.overflow = 'hidden';
    }

    function closeDrawer() {
      overlay.classList.remove('open');
      document.body.style.overflow = '';
    }

    openBtn.addEventListener('click', openDrawer);
    if (closeBtn) closeBtn.addEventListener('click', closeDrawer);

    // Close on overlay click (not drawer itself)
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeDrawer();
    });

    // Close on Escape key
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && overlay.classList.contains('open')) {
        closeDrawer();
      }
    });

    // Expose globally for use inside propose workflow
    window._openPatchDrawer = openDrawer;
  }

  // ─── Sheet tabs (inside drawer) ───
  function initSheetTabs() {
    const tabs = [
      { btn: 'proposedTabBtn', view: 'proposedView' },
      { btn: 'queueTabBtn', view: 'queueView' },
      { btn: 'reportTabBtn', view: 'reportView' },
    ];

    tabs.forEach(({ btn: btnId, view: viewId }) => {
      const btn = document.getElementById(btnId);
      if (!btn) return;

      btn.addEventListener('click', () => {
        if (btn.disabled) return;

        tabs.forEach(({ btn: otherId, view: otherViewId }) => {
          const otherBtn = document.getElementById(otherId);
          const otherView = document.getElementById(otherViewId);
          if (otherBtn) otherBtn.classList.remove('active');
          if (otherView) otherView.classList.remove('active');
        });

        btn.classList.add('active');
        const view = document.getElementById(viewId);
        if (view) view.classList.add('active');
      });
    });
  }

  // ─── Simulate workflow on "Propose Changes" ───
  function initProposeWorkflow() {
    const proposeBtn = document.getElementById('proposeButton');
    const resetBtn = document.getElementById('resetButton');
    const bulkBtn = document.getElementById('bulkApproveButton');
    const applyBtn = document.getElementById('applyButton');
    const badge = document.getElementById('timelineBadge');
    const activityLog = document.getElementById('activityLog');
    const activityChip = document.getElementById('activityChip');
    const proposedMetric = document.getElementById('proposedMetric');
    const approvedMetric = document.getElementById('approvedMetric');
    const recoverableMetric = document.getElementById('recoverableMetric');
    const kpiOutstanding = document.getElementById('kpiOutstanding');
    const kpiAtRisk = document.getElementById('kpiAtRisk');
    const kpiRecovery = document.getElementById('kpiRecovery');
    const healthFill = document.getElementById('healthFill');
    const healthLabel = document.getElementById('healthLabel');
    const mappingCount = document.getElementById('mappingCount');
    const proposedBody = document.getElementById('proposedBody');
    const statusMessage = document.getElementById('statusMessage');

    if (!proposeBtn) return;

    const SAMPLE_PATCHES = [
      { id: 'P-001', row: 3, customer: 'MedLabs Pvt Ltd', field: 'Status', before: 'Open', after: 'Follow Up', reason: 'Invoice 72 days overdue, no recent contact', confidence: '92%', impact: '₹2,80,000', risk: 'low', context: 'Last contact: 45 days ago' },
      { id: 'P-002', row: 3, customer: 'MedLabs Pvt Ltd', field: 'Priority', before: 'Normal', after: 'Critical', reason: '>60 days overdue + high value', confidence: '95%', impact: '₹2,80,000', risk: 'low', context: 'Matches SOP rule: Critical = >60d' },
      { id: 'P-003', row: 5, customer: 'DiagCorp Services', field: 'Next Action', before: '—', after: 'Call by 4pm today', reason: 'Promise-to-pay expired 3 days ago', confidence: '88%', impact: '₹1,45,000', risk: 'medium', context: 'PTP was for ₹1.45L on Mar 28' },
      { id: 'P-004', row: 7, customer: 'HealthPath Labs', field: 'Status', before: 'Disputed', after: 'Partial Paid', reason: 'Payment of ₹60K received on Apr 1', confidence: '97%', impact: '₹60,000', risk: 'low', context: 'Bank ref: NEFT-20260401-HP' },
      { id: 'P-005', row: 7, customer: 'HealthPath Labs', field: 'Amount', before: '₹1,20,000', after: '₹60,000', reason: 'Adjust outstanding after partial payment', confidence: '99%', impact: '₹60,000', risk: 'low', context: 'Remaining balance after ₹60K payment' },
      { id: 'P-006', row: 9, customer: 'CityLab Diagnostics', field: 'Priority', before: 'Low', after: 'Medium', reason: 'Approaching 30-day threshold', confidence: '85%', impact: '₹95,000', risk: 'medium', context: 'Due date: Mar 8, currently 27 days' },
    ];

    proposeBtn.addEventListener('click', () => {
      proposeBtn.disabled = true;
      if (badge) { badge.textContent = 'Running'; badge.className = 'status-pill running'; }
      if (activityChip) activityChip.textContent = 'Active';
      if (statusMessage) statusMessage.textContent = 'Agent is reading sheet and generating patches…';

      // Simulate step-by-step workflow
      const steps = document.querySelectorAll('.timeline li');

      // Step 1: Read sheet data
      setTimeout(() => {
        if (steps[0]) steps[0].querySelector('.step-index').style.background = 'var(--accent-soft)';
        addActivity('Reading sheet data from "Receivables Raw"…');
      }, 300);

      // Step 2: Map columns
      setTimeout(() => {
        if (steps[0]) steps[0].querySelector('.step-index').style.background = 'var(--ok-soft)';
        if (steps[1]) steps[1].querySelector('.step-index').style.background = 'var(--accent-soft)';
        addActivity('Mapped 6 columns: Customer Name, Invoice #, Amount, Due Date, Status, Days Overdue');
        if (mappingCount) mappingCount.textContent = '6 mapped';
      }, 1200);

      // Step 3: Generate patches
      setTimeout(() => {
        if (steps[1]) steps[1].querySelector('.step-index').style.background = 'var(--ok-soft)';
        if (steps[2]) steps[2].querySelector('.step-index').style.background = 'var(--accent-soft)';
        addActivity('AI analyzing rows… found 6 patch candidates');
      }, 2200);

      // Step 4: Patches ready — populate + open drawer
      setTimeout(() => {
        if (steps[2]) steps[2].querySelector('.step-index').style.background = 'var(--ok-soft)';
        if (steps[3]) steps[3].querySelector('.step-index').style.background = 'var(--accent-soft)';
        addActivity('Generated 6 patches across 4 customers');

        // Populate the table
        if (proposedBody) {
          proposedBody.innerHTML = '';
          SAMPLE_PATCHES.forEach((p, i) => {
            const tr = document.createElement('tr');
            tr.style.opacity = '0';
            tr.style.transform = 'translateY(6px)';
            tr.innerHTML = `
              <td><input type="checkbox" checked /></td>
              <td><code>${p.id}</code></td>
              <td>${p.row}</td>
              <td><strong>${p.customer}</strong></td>
              <td>${p.field}</td>
              <td style="color: var(--ink-muted)">${p.before}</td>
              <td style="color: var(--brand); font-weight: 600">${p.after}</td>
              <td style="max-width: 24ch; color: var(--ink-secondary); font-size: 0.82rem;">${p.reason}</td>
              <td>${p.confidence}</td>
              <td>${p.impact}</td>
              <td><span class="risk-badge ${p.risk}">${p.risk}</span></td>
              <td style="font-size: 0.8rem; color: var(--ink-muted)">${p.context}</td>
            `;
            proposedBody.appendChild(tr);

            // Stagger animation
            setTimeout(() => {
              tr.style.transition = 'opacity 300ms var(--ease-out), transform 300ms var(--ease-out)';
              tr.style.opacity = '1';
              tr.style.transform = 'translateY(0)';
            }, 50 * i);
          });
        }

        // Update metrics
        if (proposedMetric) proposedMetric.textContent = '6';
        if (kpiOutstanding) kpiOutstanding.textContent = '₹18,42,000';
        if (kpiAtRisk) kpiAtRisk.textContent = '₹6,20,000';
        if (kpiRecovery) kpiRecovery.textContent = '₹4,80,000';

        // Health fill
        if (healthFill) {
          healthFill.style.width = '62%';
          healthFill.style.background = 'linear-gradient(90deg, #c44536, #f39c12)';
        }
        if (healthLabel) healthLabel.textContent = 'Moderate — 5 accounts need attention';

        // Aging buckets
        const fills = document.querySelectorAll('.bucket-fill');
        const values = document.querySelectorAll('.bucket-value');
        if (fills.length >= 4) {
          fills[0].style.width = '65%'; if (values[0]) values[0].textContent = '₹11.9L';
          fills[1].style.width = '25%'; fills[1].style.background = 'var(--accent)'; if (values[1]) values[1].textContent = '₹4.6L';
          fills[2].style.width = '8%'; fills[2].style.background = 'var(--danger)'; if (values[2]) values[2].textContent = '₹1.5L';
          fills[3].style.width = '3%'; fills[3].style.background = '#8e2415'; if (values[3]) values[3].textContent = '₹0.3L';
        }

        // Enable buttons
        if (bulkBtn) bulkBtn.disabled = false;
        if (applyBtn) applyBtn.disabled = false;

        if (badge) { badge.textContent = 'Review'; badge.className = 'status-pill complete'; }
        if (activityChip) activityChip.textContent = '6 actions';
        if (statusMessage) statusMessage.textContent = '6 patches ready — click Review Patches to review.';

        showToast('6 patches proposed — click Review Patches');

        // Auto-open the drawer after a tiny delay for the toast
        setTimeout(() => {
          if (window._openPatchDrawer) window._openPatchDrawer();
        }, 400);
      }, 3200);
    });

    // Bulk approve
    if (bulkBtn) {
      bulkBtn.addEventListener('click', () => {
        if (approvedMetric) approvedMetric.textContent = '4';
        addActivity('Bulk approved 4 low-risk patches');
        showToast('4 low-risk patches approved');
        bulkBtn.disabled = true;
      });
    }

    // Apply
    if (applyBtn) {
      applyBtn.addEventListener('click', () => {
        if (approvedMetric) approvedMetric.textContent = '6';
        if (recoverableMetric) recoverableMetric.textContent = '₹4,80,000';
        addActivity('Applied 6 patches to Google Sheet');

        if (badge) { badge.textContent = 'Applied'; badge.className = 'status-pill applied'; }
        if (statusMessage) statusMessage.textContent = 'All patches applied. Check Collections Queue and Report tabs.';

        // Enable other tabs
        const queueTab = document.getElementById('queueTabBtn');
        const reportTab = document.getElementById('reportTabBtn');
        if (queueTab) queueTab.disabled = false;
        if (reportTab) reportTab.disabled = false;

        showToast('All patches applied to sheet ✓');
        applyBtn.disabled = true;
      });
    }

    // Reset
    if (resetBtn) {
      resetBtn.addEventListener('click', () => {
        location.reload();
      });
    }

    function addActivity(text) {
      if (!activityLog) return;
      // Clear the "waiting" message on first activity
      if (activityLog.children.length === 1 && activityLog.children[0].textContent.includes('Waiting')) {
        activityLog.innerHTML = '';
      }
      const li = document.createElement('li');
      li.textContent = text;
      li.style.opacity = '0';
      li.style.transform = 'translateY(4px)';
      activityLog.appendChild(li);

      requestAnimationFrame(() => {
        li.style.transition = 'opacity 300ms var(--ease-out), transform 300ms var(--ease-out)';
        li.style.opacity = '1';
        li.style.transform = 'translateY(0)';
      });
    }
  }

  // ─── Button press feedback ───
  function initButtonFeedback() {
    document.querySelectorAll('button').forEach((btn) => {
      btn.addEventListener('click', (e) => {
        if (btn.disabled) return;
        const rect = btn.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        const ripple = document.createElement('span');
        ripple.style.cssText = `
          position: absolute; width: 0; height: 0;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.25);
          transform: translate(-50%, -50%);
          left: ${x}px; top: ${y}px;
          pointer-events: none;
        `;

        btn.style.position = 'relative';
        btn.style.overflow = 'hidden';
        btn.appendChild(ripple);

        ripple.animate(
          [
            { width: '0px', height: '0px', opacity: 1 },
            { width: '300px', height: '300px', opacity: 0 },
          ],
          { duration: 500, easing: 'cubic-bezier(0.23, 1, 0.32, 1)', fill: 'forwards' }
        ).onfinish = () => ripple.remove();
      });
    });
  }

  // ─── Init ───
  function init() {
    initThemeToggle();
    initScrollNav();
    initPromptTabs();
    initDrawer();
    initSheetTabs();
    initProposeWorkflow();
    initButtonFeedback();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
