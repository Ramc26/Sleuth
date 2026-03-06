/**
 * Sleuth — App State & UI Controller  |  app.js v3.0
 * Parallel batch PDF processing · Invoice card list · Detail panel · FA icons
 */

/* ════════════════════════════════════════════════
   Health Check (Qdrant)
   ════════════════════════════════════════════════ */
function checkHealth() {
    const $btn = $('#sysWarningRetry');
    $btn.prop('disabled', true).html('<i class="fa-solid fa-rotate fa-spin"></i> Checking…');

    $.getJSON('/api/health')
        .done(function (res) {
            if (res.ok) {
                $('#sysWarning').fadeOut(300);
            } else if (!res.qdrant.reachable) {
                showBanner(
                    'Vector Store Offline',
                    res.qdrant.error || 'Qdrant is not reachable. Start Docker to enable forensic investigation.',
                    false
                );
            } else {
                showBanner(
                    'Evidence Base Not Indexed',
                    res.qdrant.error || "Click 'Sync Evidence Base' in the sidebar to index your evidence files.",
                    true
                );
            }
        })
        .fail(function () {
            showBanner('Health Check Failed', 'Could not reach the Sleuth backend. Is Uvicorn running?', false);
        })
        .always(function () {
            $btn.prop('disabled', false).html('<i class="fa-solid fa-rotate"></i> Retry');
        });
}

function showBanner(title, msg, isCollectionWarning) {
    $('#sysWarningTitle').text(title);
    $('#sysWarningMsg').text(msg);
    $('#sysWarning')
        .toggleClass('warn-collection', isCollectionWarning)
        .show();
}

/* ════════════════════════════════════════════════
   State
   ════════════════════════════════════════════════ */
const State = {
    results: {},    // keyed by file index: {file, status, data, pdfUrl}
    activeIdx: null,  // which invoice is shown in the detail panel
    sessionHistory: [],
};

/* ════════════════════════════════════════════════
   Tab Navigation
   ════════════════════════════════════════════════ */
function switchTab(tabKey) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${tabKey}`).classList.add('active');
    const navMap = { capture: 'navDataEntry', analysis: 'navAuditSuite', payroll: 'navPayroll' };
    document.getElementById(navMap[tabKey]).classList.add('active');
}

/* ════════════════════════════════════════════════
   Main Document Ready
   ════════════════════════════════════════════════ */
$(function () {

    // Health check on load + poll every 30 s
    checkHealth();
    setInterval(checkHealth, 30_000);

    /* ─── Drag & Drop ──────────────────────────────────────────── */
    const $dz = $('#invoiceDropzone');

    $dz.on('dragover dragenter', e => { e.preventDefault(); $dz.addClass('dragover'); })
        .on('dragleave drop', e => {
            e.preventDefault();
            $dz.removeClass('dragover');
            if (e.type === 'drop') {
                const files = Array.from(e.originalEvent.dataTransfer.files)
                    .filter(f => f.name.toLowerCase().endsWith('.pdf'));
                if (files.length) startBatch(files);
                else showToast('Only PDF files are accepted.', 'error');
            }
        });

    $('#invoiceFileInput').on('change', function () {
        const files = Array.from(this.files);
        if (files.length) startBatch(files);
        this.value = '';
    });

    /* ─── Batch Processing (all files in parallel) ─────────────── */
    function startBatch(files) {
        // Reset state
        State.results = {};
        State.activeIdx = null;

        files.forEach((f, i) => {
            State.results[i] = { file: f, status: 'processing', data: null, pdfUrl: null };
        });

        renderQueueList();
        $('#captureWorkspace').show();
        showDetailEmpty();

        // Update batch counter
        updateBatchCounter();

        // Upload all files simultaneously — no waiting
        files.forEach((f, i) => uploadFile(f, i));
    }

    function uploadFile(file, idx) {
        const formData = new FormData();
        formData.append('file', file);

        $.ajax({
            url: '/api/upload_invoice',
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function (res) {
                State.results[idx].status = 'done';
                State.results[idx].data = res.data;
                State.results[idx].pdfUrl = res.pdf_url;
                updateCard(idx);
                updateBatchCounter();

                // Auto-open the first successfully extracted invoice
                const processedCount = Object.values(State.results).filter(r => r.status !== 'processing').length;
                if (processedCount === 1 && State.activeIdx === null) {
                    openDetail(idx);
                }
            },
            error: function (err) {
                const detail = err.responseJSON?.detail || 'Extraction failed.';
                State.results[idx].status = 'error';
                State.results[idx].errorMsg = detail;
                updateCard(idx);
                updateBatchCounter();
            }
        });
    }

    function updateBatchCounter() {
        const total = Object.keys(State.results).length;
        const done = Object.values(State.results).filter(r => r.status !== 'processing').length;
        $('#batchCountText').text(`${done} / ${total} processed`);
        if (total > 0) $('#batchCounter').show();
    }

    /* ─── Queue List Rendering ─────────────────────────────────── */
    function renderQueueList() {
        const $body = $('#queueListBody').empty();
        const total = Object.keys(State.results).length;
        $('#queueListBadge').text(`${total} document${total !== 1 ? 's' : ''}`);

        Object.entries(State.results).forEach(([idx, r]) => {
            $body.append(buildCard(parseInt(idx), r));
        });
    }

    function updateCard(idx) {
        const r = State.results[idx];
        const $old = $(`#inv-card-${idx}`);
        const $new = buildCard(idx, r);
        if ($old.length) $old.replaceWith($new);
        else $('#queueListBody').append($new);
    }

    function buildCard(idx, r) {
        const isActive = State.activeIdx === idx;
        let chipHtml, bodyHtml;

        if (r.status === 'processing') {
            chipHtml = '<span class="inv-chip chip-processing">Processing</span>';
            bodyHtml = `<div class="inv-card-processing">
                            <div class="inv-card-spinner"></div>
                            Extracting data…
                        </div>`;
        } else if (r.status === 'error') {
            chipHtml = '<span class="inv-chip chip-error">Failed</span>';
            bodyHtml = `<div style="font-size:11px;color:var(--red);margin-top:4px;">${r.errorMsg || 'Extraction error.'}</div>`;
        } else if (r.status === 'posted') {
            const d = r.data;
            chipHtml = '<span class="inv-chip chip-posted">Posted</span>';
            bodyHtml = `<div class="inv-card-id">${d.invoice_id || '—'}</div>
                        <div class="inv-card-meta">${d.entity || '—'}</div>
                        <div class="inv-card-amount">${fmtAmount(d.amount, d.currency)}</div>`;
        } else {
            const d = r.data;
            chipHtml = '<span class="inv-chip chip-done">Parsed</span>';
            bodyHtml = `<div class="inv-card-id">${d.invoice_id || '—'}</div>
                        <div class="inv-card-meta">${d.entity || '—'}</div>
                        <div class="inv-card-amount">${fmtAmount(d.amount, d.currency)}</div>`;
        }

        return $(`
            <div class="inv-card${isActive ? ' active' : ''}" id="inv-card-${idx}"
                 onclick="openDetail(${idx})"
                 title="${r.file.name}">
                <div class="inv-card-top">
                    <span class="inv-card-filename">${r.file.name}</span>
                    ${chipHtml}
                </div>
                ${bodyHtml}
            </div>
        `);
    }

    /* ─── Detail Panel ─────────────────────────────────────────── */
    window.openDetail = function (idx) {
        const r = State.results[idx];
        if (!r || r.status === 'processing') return;

        State.activeIdx = idx;
        // Update active state on cards
        $('.inv-card').removeClass('active');
        $(`#inv-card-${idx}`).addClass('active');

        if (r.status === 'error') {
            showDetailEmpty(`<i class="fa-solid fa-triangle-exclamation" style="color:var(--red)"></i><br>${r.errorMsg || 'Extraction failed for this document.'}`);
            return;
        }

        // Populate PDF viewer
        $('#pdfEmbed').attr('src', r.pdfUrl);
        $('#detailFilename').text(r.file.name);

        // Populate core fields
        const d = r.data;
        $('#extInvoiceId').val(d.invoice_id || '');
        $('#extEntity').val(d.entity || '');
        $('#extAmount').val(d.amount != null ? parseFloat(d.amount).toFixed(2) : '');
        $('#extDate').val(d.date || '');

        // Extended fields
        $('#extBillingPeriod').val(d.billing_period || '');
        $('#extAccountNumber').val(d.account_number || '');
        $('#extCurrency').val(d.currency || '');
        $('#extTax').val(d.tax != null ? parseFloat(d.tax).toFixed(2) : '');
        $('#extCredits').val(d.credits != null ? parseFloat(d.credits).toFixed(2) : '');
        $('#extBillTo').val(d.bill_to || '');

        // Service breakdown
        const $bt = $('#breakdownTable').empty();
        if (d.service_breakdown && Object.keys(d.service_breakdown).length > 0) {
            Object.entries(d.service_breakdown).forEach(([svc, amt]) => {
                $bt.append(`<div class="breakdown-row">
                    <span class="breakdown-svc">${svc}</span>
                    <span class="breakdown-amt">${fmtAmount(amt, d.currency)}</span>
                </div>`);
            });
        } else {
            $bt.html('<p class="breakdown-empty">No line items extracted.</p>');
        }

        // Badge state
        const isPosted = r.status === 'posted';
        $('#extractionBadge')
            .toggleClass('posted-badge', isPosted)
            .html(isPosted
                ? '<i class="fa-solid fa-check-double"></i> Posted to Ledger'
                : '<i class="fa-solid fa-circle-check"></i> Extraction Complete'
            );
        $('#confirmSaveBtn').prop('disabled', isPosted)
            .html(isPosted
                ? '<i class="fa-solid fa-check-double"></i> Posted'
                : '<i class="fa-solid fa-check"></i> Post to Ledger'
            );
        $('#reExtractBtn').prop('disabled', isPosted);
        $('#discardBtn').prop('disabled', isPosted);

        $('#detailEmpty').hide();
        $('#detailContent').show();
        $('#saveToast').hide();
    };

    function showDetailEmpty(msg) {
        $('#detailContent').hide();
        if (msg) {
            $('#detailEmpty').html(`<div class="detail-empty-icon" style="font-size:44px;opacity:.2;margin-bottom:12px">${msg}</div>`);
        } else {
            $('#detailEmpty').html(`
                <i class="fa-regular fa-file-lines detail-empty-icon"></i>
                <p>Select a document from the queue to review extracted data.</p>
            `);
        }
        $('#detailEmpty').show();
    }

    /* ─── Re-process ───────────────────────────────────────────── */
    $('#reExtractBtn').on('click', function () {
        const idx = State.activeIdx;
        if (idx === null) return;

        const r = State.results[idx];
        r.status = 'processing';
        r.data = null;
        r.pdfUrl = null;

        $(this).prop('disabled', true);
        showDetailEmpty();
        updateCard(idx);
        uploadFile(r.file, idx);
    });

    /* ─── Post to Ledger ───────────────────────────────── */
    $('#confirmSaveBtn').on('click', function () {
        const idx = State.activeIdx;
        if (idx === null) return;

        const r = State.results[idx];
        if (r.status !== 'done') return;

        const $btn = $(this);
        $btn.prop('disabled', true).html('<span class="spinner-border"></span> Posting…');

        const payload = {
            invoice_id: $('#extInvoiceId').val().trim(),
            entity: $('#extEntity').val().trim(),
            amount: parseFloat($('#extAmount').val()) || 0,
            date: $('#extDate').val().trim(),
            billing_period: $('#extBillingPeriod').val().trim() || null,
        };

        $.ajax({
            url: '/api/post_to_ledger',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(payload),
            success: function (res) {
                // Mark as posted in state
                r.status = 'posted';
                r.data = { ...r.data, ...payload };

                // Delete uploaded PDF from server
                if (r.pdfUrl) {
                    $.ajax({ url: `/api/invoice_pdf?pdf_url=${encodeURIComponent(r.pdfUrl)}`, type: 'DELETE' });
                }

                addToHistory(payload);
                updateCard(idx);
                openDetail(idx);
                updateBatchCounter();

                const zohoMsg = res.zoho_posted
                    ? ` &middot; Bill <code>${res.zoho_bill_id}</code> created in Zoho Books`
                    : ' &middot; CSV only (Zoho not connected)';
                showToast(`Posted &mdash; ${payload.invoice_id}${zohoMsg}`, res.zoho_posted ? 'success' : 'success');
            },
            error: function (err) {
                const detail = err.responseJSON?.detail || 'Post to Ledger failed.';
                $btn.prop('disabled', false).html('<i class="fa-solid fa-check"></i> Post to Ledger');
                showToast(detail, 'error');
            }
        });
    });

    /* ─── Reject ──────────────────────────────────────────────── */
    $('#discardBtn').on('click', function () {
        const idx = State.activeIdx;
        if (idx === null) return;

        const r = State.results[idx];
        // Delete uploaded PDF
        if (r.pdfUrl) {
            $.ajax({
                url: `/api/invoice_pdf?pdf_url=${encodeURIComponent(r.pdfUrl)}`,
                type: 'DELETE'
            });
        }

        delete State.results[idx];
        showDetailEmpty();
        updateQueueList();
        updateBatchCounter();
    });

    function updateQueueList() {
        const $body = $('#queueListBody').empty();
        const entries = Object.entries(State.results);
        $('#queueListBadge').text(`${entries.length} document${entries.length !== 1 ? 's' : ''}`);
        entries.forEach(([idx, r]) => $body.append(buildCard(parseInt(idx), r)));
    }

    /* ─── Session History ──────────────────────────────────────── */
    function addToHistory(d) {
        State.sessionHistory.unshift(d);
        if (State.sessionHistory.length > 6) State.sessionHistory.pop();

        const $list = $('#historyList').empty();
        State.sessionHistory.forEach(item => {
            $list.append(`<li class="history-item">
                <div>
                    <span class="history-inv">${item.invoice_id || '—'}</span>
                    <span class="history-meta"> · ${item.entity || '—'}</span>
                </div>
                <span class="history-amt">${fmtAmount(item.amount)}</span>
            </li>`);
        });
        $('#historyCard').show();
    }

    /* ─── Toast ────────────────────────────────────────────────── */
    function showToast(msg, type) {
        const $t = $('#saveToast');
        $t.removeClass('success error').addClass(type).html(msg).show();
        setTimeout(() => $t.fadeOut(), 4000);
    }


    /* ────────────────────────────────────────────────────────────
       TAB 2 — VARIANCE ANALYSIS
    ─────────────────────────────────────────────────────────────── */

    $('#reconcileForm').on('submit', function (e) {
        e.preventDefault();
        const fileA = $('#fileA')[0].files[0];
        const fileB = $('#fileB')[0].files[0];
        if (!fileA || !fileB) return;

        const fd = new FormData();
        fd.append('file_a', fileA);
        fd.append('file_b', fileB);

        const $btn = $('#reconcileBtn');
        $btn.prop('disabled', true).html('<span class="spinner-border"></span> Reconciling…');
        $('#boardTbody').html(`<tr><td colspan="5" class="empty-state">
            <i class="fa-solid fa-rotate fa-spin"></i> Merging ledgers…</td></tr>`);
        $('#reportContainer').html('<div class="audit-empty"><i class="fa-solid fa-user-secret audit-empty-icon"></i><p>Select an exception from the Variance Log<br>to initiate an AI-assisted investigation.</p></div>');
        resetAnalysisBadge();

        $.ajax({
            url: '/api/reconcile', type: 'POST',
            data: fd, processData: false, contentType: false,
            success: function (res) {
                updateKPIs(res.summary);
                renderVarianceLog(res.data);
            },
            error: function (err) {
                const detail = err.responseJSON?.detail || 'Reconciliation failed.';
                $('#boardTbody').html(`<tr><td colspan="5" class="empty-state" style="color:var(--red)">
                    <i class="fa-solid fa-triangle-exclamation"></i> ${detail}</td></tr>`);
            },
            complete: () => $btn.prop('disabled', false).html('<i class="fa-solid fa-scale-balanced"></i> Reconcile')
        });
    });

    function updateKPIs(s) {
        $('#metricTotal').text(s.total_rows);
        $('#metricFlagged').text(s.flagged);
        $('#metricRisk').text('$' + parseFloat(s.risk).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
    }

    function renderVarianceLog(rows) {
        const $tbody = $('#boardTbody').empty();
        const exceptions = rows.filter(r => r.status === 'Discrepancy');
        const matched = rows.filter(r => r.status === 'Matched');
        const ordered = [...exceptions, ...matched];

        if (!ordered.length) {
            $tbody.html('<tr><td colspan="5" class="empty-state"><i class="fa-regular fa-folder-open"></i> No matching rows after merge.</td></tr>');
            $('#boardCount').text('');
            return;
        }
        $('#boardCount').text(`${exceptions.length} exception${exceptions.length !== 1 ? 's' : ''}`);

        ordered.forEach(row => {
            const isEx = row.status === 'Discrepancy';
            const badge = isEx
                ? '<span class="status-badge badge-exception"><i class="fa-solid fa-circle-exclamation"></i> Exception</span>'
                : '<span class="status-badge badge-matched"><i class="fa-solid fa-circle-check"></i> Matched</span>';
            const varanceHtml = isEx
                ? `<span class="variance-neg">$${Math.abs(parseFloat(row.Variance)).toFixed(2)}</span>`
                : `<span class="variance-zero">—</span>`;
            const action = isEx
                ? `<button class="btn-open-case"
                        data-inv="${row.invoice_id}" data-ent="${row.entity}"
                        data-amta="${row.amount_SubA}" data-amtb="${row.amount_SubB}">
                        <i class="fa-solid fa-magnifying-glass"></i> Open Case
                   </button>`
                : '';

            $tbody.append(`<tr id="row-${row.invoice_id}">
                <td class="td-mono">${row.invoice_id}</td>
                <td>${row.entity}</td>
                <td>${badge}</td>
                <td>${varanceHtml}</td>
                <td>${action}</td>
            </tr>`);
        });
    }

    /* ─── Open Case (Investigation) ────────────────────────────── */
    let activeCase = null;

    $(document).on('click', '.btn-open-case', function () {
        const $btn = $(this);
        const inv_id = $btn.data('inv');
        if (activeCase === inv_id) return;
        activeCase = inv_id;

        const entity = $btn.data('ent');
        const amt_a = parseFloat($btn.data('amta'));
        const amt_b = parseFloat($btn.data('amtb'));

        $('#boardTbody tr').removeClass('active-row');
        $(`#row-${inv_id}`).addClass('active-row');
        $('.btn-open-case').prop('disabled', true);
        $btn.html('<span class="spinner-border"></span>');

        const $status = $('#investigationStatus');
        $status.removeClass('status-resolved status-error').addClass('status-investigating')
            .text(`Investigating ${inv_id}…`);

        $('#reportContainer').html(`<div class="audit-empty">
            <div class="spinner-border text-primary mb-3" style="width:26px;height:26px;border-width:2.5px"></div>
            <p style="font-weight:700;color:var(--text-1);font-size:13px">Analysing variance…</p>
            <p style="font-size:11.5px;color:var(--text-2)">Querying Qdrant &middot; Generating Audit Report</p>
        </div>`);

        $.ajax({
            url: '/api/investigate', type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ invoice_id: inv_id, entity, amount_a: amt_a, amount_b: amt_b }),
            success: function (res) {
                $('#reportContainer').html(marked.parse(res.report));
                $status.removeClass('status-investigating').addClass('status-resolved').text('Resolved');
            },
            error: function (err) {
                const detail = err.responseJSON?.detail || 'An unexpected error occurred.';
                const statusCode = err.status;
                const icon = statusCode === 503 && detail.includes('Offline')
                    ? '<i class="fa-solid fa-server" style="font-size:32px;color:var(--red);opacity:.4;margin-bottom:12px;display:block"></i>'
                    : '<i class="fa-solid fa-triangle-exclamation" style="font-size:32px;color:var(--amber);opacity:.6;margin-bottom:12px;display:block"></i>';
                const heading = statusCode === 503 && detail.includes('Offline') ? 'Vector Store Offline'
                    : statusCode === 503 ? 'Evidence Base Not Indexed'
                        : 'Investigation Error';
                const hint = statusCode === 503
                    ? '<br><small style="opacity:.65">Run <code>docker run -p 6333:6333 qdrant/qdrant</code> then click "Sync Evidence Base".</small>'
                    : '';
                $('#reportContainer').html(`<div style="padding:22px">${icon}
                    <p style="font-weight:700;font-size:14px;color:var(--text-1);margin-bottom:7px">${heading}</p>
                    <p style="font-size:12.5px;color:var(--text-2);line-height:1.65">${detail}${hint}</p>
                </div>`);
                $status.removeClass('status-investigating').addClass('status-error').text('Error');
                if (statusCode === 503) checkHealth();
            },
            complete: function () {
                $btn.html('<i class="fa-solid fa-magnifying-glass"></i> Open Case').prop('disabled', false);
                $('.btn-open-case').prop('disabled', false);
                activeCase = null;
            }
        });
    });

    function resetAnalysisBadge() {
        $('#investigationStatus').text('Awaiting Selection')
            .removeClass('status-investigating status-resolved status-error');
    }

    /* ─── Sync Evidence Base ────────────────────────────────────── */
    $('#indexDbBtn').on('click', function () {
        const $btn = $(this);
        $btn.prop('disabled', true);
        $('#syncBtnText').text('Syncing…');

        $.post('/api/index_db')
            .done(() => { $('#syncBtnText').text('Synced'); checkHealth(); })
            .fail(() => $('#syncBtnText').text('Sync Failed'))
            .always(() => {
                $btn.prop('disabled', false);
                setTimeout(() => $('#syncBtnText').text('Sync Evidence Base'), 3000);
            });
    });

    /* ─── Utilities ───────────────────────────────────────── */
    function fmtAmount(val, currency) {
        if (val == null || isNaN(val)) return '—';
        const sym = currency === 'INR' ? '₹' : currency === 'GBP' ? '£' : currency === 'EUR' ? '€' : '$';
        return sym + parseFloat(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    /* ─── Zoho Status (called on page load) ────────────────────── */
    checkZohoStatus();

    // If redirected back after successful OAuth
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('zoho_connected') === '1') {
        showToast('<i class="fa-solid fa-check-circle"></i> Zoho Books connected successfully!', 'success');
        window.history.replaceState({}, '', '/');
    }

});

/* ───────────────────────────────────────────────────────────────────────
   Zoho Status + Disconnect (global scope — called from HTML onclick)
────────────────────────────────────────────────────────────────────── */

function checkZohoStatus() {
    $.getJSON('/api/zoho/status')
        .done(function (res) {
            const $dot = $('.zoho-dot');
            const $text = $('#zohoStatusText');
            if (res.connected) {
                $dot.removeClass('dot-disconnected').addClass('dot-connected');
                $text.text(`Org ${res.org_id || 'Connected'}`);
                $('#zohoConnectActions').hide();
                $('#zohoDisconnectActions').show();
            } else {
                $dot.removeClass('dot-connected').addClass('dot-disconnected');
                $text.text('Disconnected');
                $('#zohoConnectActions').show();
                $('#zohoDisconnectActions').hide();
            }
        })
        .fail(function () {
            $('#zohoStatusText').text('Status unknown');
        });
}

function disconnectZoho() {
    $.post('/api/zoho/disconnect')
        .done(function () {
            checkZohoStatus();
        })
        .fail(function () {
            alert('Disconnect failed.');
        });
}

/* ═══════════════════════════════════════════════════════════════════
   TAB 3 — PAYROLL ENGINE
   ═══════════════════════════════════════════════════════════════════ */

/* ── State ──────────────────────────────────────────────────────── */
const Payroll = {
    allRows: [],        // full dataset from API
    filtered: [],       // after filters applied
    hiddenGroups: {},   // group → bool
};

/* ── Upload trigger ─────────────────────────────────────────────── */
$(function () {

    /* Drag & drop on payroll upload zone */
    const $pz = $('#payrollUploadZone');

    $pz.on('dragover dragenter', e => { e.preventDefault(); $pz.css('border-color', 'var(--accent)'); })
       .on('dragleave', ()      => $pz.css('border-color', ''))
       .on('drop', e => {
           e.preventDefault();
           $pz.css('border-color', '');
           const file = e.originalEvent.dataTransfer.files[0];
           if (file && file.name.endsWith('.csv')) processPayrollFile(file);
       });

    $('#payrollFileInput').on('change', function () {
        if (this.files[0]) processPayrollFile(this.files[0]);
        this.value = '';
    });
});

/* ── Upload & process ───────────────────────────────────────────── */
function processPayrollFile(file) {
    $('#payrollUploadZone').hide();
    $('#payrollProcessing').show();
    $('#payrollResults').hide();
    $('#payrollHeaderActions').hide();

    const fd = new FormData();
    fd.append('attendance_file', file);

    $.ajax({
        url: '/api/payroll/process',
        type: 'POST',
        data: fd,
        processData: false,
        contentType: false,
        success: function (res) {
            Payroll.allRows = res.employees;
            Payroll.filtered = [...Payroll.allRows];

            renderPayrollKPIs(res.summary);
            populateDeptFilter(res.employees);
            renderPayrollTable(res.employees);

            $('#payrollProcessing').hide();
            $('#payrollResults').show();
            $('#payrollHeaderActions').show();
        },
        error: function (err) {
            $('#payrollProcessing').hide();
            $('#payrollUploadZone').show();
            const msg = err.responseJSON?.detail || 'Payroll processing failed.';
            alert('Error: ' + msg);
        }
    });
}

/* ── KPIs ───────────────────────────────────────────────────────── */
function renderPayrollKPIs(s) {
    $('#pkActive').text(s.active_count);
    $('#pkHeadcountSub').text(`${s.total_headcount} total · ${s.resigned_count} resigned`);

    $('#pkGross').text(inr(s.total_gross));
    $('#pkGrossSub').text(`Bonus ₹${fmt(s.total_bonus)} · Gratuity ₹${fmt(s.total_gratuity)}`);

    $('#pkNet').text(inr(s.total_net));
    $('#pkNetSub').text(`After all deductions`);

    const totalStatutory = s.total_epf_emp + s.total_esi_emp;
    $('#pkStatutory').text(inr(totalStatutory));
    $('#pkStatutorySub').text(`EPF ₹${fmt(s.total_epf_emp)} · ESI ₹${fmt(s.total_esi_emp)}`);

    $('#pkCTC').text(inr(s.total_ctc));
    $('#pkCTCSub').text(`Incl. employer contributions ₹${fmt(s.total_employer)}`);

    /* Stats strip */
    const strip = $('#pkStatsStrip').empty();
    if (s.resigned_count)   strip.append(pill('resigned',  `<i class="fa-solid fa-right-from-bracket"></i> ${s.resigned_count} Resigned`));
    if (s.maternity_count)  strip.append(pill('maternity', `<i class="fa-solid fa-baby"></i> ${s.maternity_count} Maternity`));
    if (s.long_leave_count) strip.append(pill('longleave', `<i class="fa-solid fa-person-walking-arrow-right"></i> ${s.long_leave_count} Long Leave`));
    if (s.total_bonus  > 0) strip.append(pill('bonus',   `<i class="fa-solid fa-gift"></i> Bonus ₹${fmt(s.total_bonus)}`));
    if (s.total_gratuity>0) strip.append(pill('gratuity',`<i class="fa-solid fa-star"></i> Gratuity ₹${fmt(s.total_gratuity)}`));
}

function pill(cls, html) {
    return `<span class="pr-stat-pill ${cls}">${html}</span>`;
}

/* ── Dept filter options ────────────────────────────────────────── */
function populateDeptFilter(rows) {
    const depts = [...new Set(rows.map(r => r.customer).filter(Boolean))].sort();
    const $sel = $('#filterDept').empty().append('<option value="">All</option>');
    depts.forEach(d => $sel.append(`<option value="${d}">${d}</option>`));
}

/* ── Filters ────────────────────────────────────────────────────── */
window.applyPayrollFilters = function () {
    const status  = $('#filterStatus').val().toLowerCase();
    const dept    = $('#filterDept').val().toLowerCase();
    const search  = $('#payrollSearch').val().toLowerCase().trim();

    Payroll.filtered = Payroll.allRows.filter(r => {
        if (status && r.status.toLowerCase() !== status) return false;
        if (dept   && r.customer.toLowerCase() !== dept)  return false;
        if (search && !r.emp_id.toLowerCase().includes(search) &&
                      !r.email.toLowerCase().includes(search)  &&
                      !(r.name || '').toLowerCase().includes(search)) return false;
        return true;
    });

    renderPayrollTable(Payroll.filtered);
};

/* ── Column group toggle ────────────────────────────────────────── */
window.toggleColGroup = function (btn) {
    const group = btn.dataset.group;
    const nowActive = !btn.classList.contains('active');
    btn.classList.toggle('active', nowActive);
    Payroll.hiddenGroups[group] = !nowActive;

    $(`#payrollTable [data-group="${group}"]`).toggleClass('col-hidden', !nowActive);
};

/* ── Table render ───────────────────────────────────────────────── */
function renderPayrollTable(rows) {
    const $tbody = $('#payrollTbody').empty();

    if (!rows.length) {
        $tbody.html('<tr><td colspan="39" class="empty-state"><i class="fa-regular fa-folder-open"></i> No results match the current filters.</td></tr>');
        $('#prRowCount').text('');
        return;
    }

    /* Re-apply hidden groups to newly rendered header cells */
    Object.entries(Payroll.hiddenGroups).forEach(([group, hidden]) => {
        $(`#payrollTable th[data-group="${group}"]`).toggleClass('col-hidden', hidden);
    });

    rows.forEach((e, i) => {
        const statusCls = {
            Active: 'ps-active', Resigned: 'ps-resigned',
            Maternity: 'ps-maternity', 'Long Leave': 'ps-longleave'
        }[e.status] || 'ps-active';

        const statusIcon = {
            Active: 'fa-circle-check', Resigned: 'fa-right-from-bracket',
            Maternity: 'fa-baby', 'Long Leave': 'fa-person-walking-arrow-right'
        }[e.status] || 'fa-circle-check';

        const tdsVal       = parseFloat(e.tds || 0);
        const insVal       = parseFloat(e.insurance || 0);
        const otherVal     = parseFloat(e.other || 0);

        $tbody.append(`
        <tr data-emp="${e.emp_id}">
            <td class="td-num">${i + 1}</td>
            <td class="td-emp">${e.emp_id}</td>
            <td><span class="ps-badge ${statusCls}"><i class="fa-solid ${statusIcon}"></i> ${e.status}</span></td>

            <td data-group="contact" class="td-email">
                <a href="mailto:${e.email}" title="${e.email}">${e.email || '—'}</a>
            </td>
            <td data-group="contact" class="td-num" style="text-align:left">${e.mobile || '—'}</td>
            <td data-group="contact">${e.doj || '—'}</td>
            <td data-group="contact">${e.doe || '—'}</td>
            <td data-group="contact" style="max-width:140px;overflow:hidden;text-overflow:ellipsis">${e.customer || '—'}</td>

            <td data-group="attendance" class="td-num">${e.present}</td>
            <td data-group="attendance" class="td-num">${e.wo}</td>
            <td data-group="attendance" class="td-num">${e.leaves}</td>
            <td data-group="attendance" class="td-num">${e.hfl || zeroCell(0)}</td>
            <td data-group="attendance" class="td-num">${e.ml  || zeroCell(0)}</td>
            <td data-group="attendance" class="td-num ${e.ul  > 0 ? '' : 'td-zero'}">${e.ul}</td>
            <td data-group="attendance" class="td-num ${e.lop > 0 ? 'td-money' : 'td-zero'}" style="color:${e.lop>0?'var(--red)':''}">${e.lop}</td>
            <td data-group="attendance" class="td-num" style="font-weight:700">${e.payable_days}</td>

            <td data-group="leave" class="td-num">${e.open_cl}</td>
            <td data-group="leave" class="td-num">${e.open_sl}</td>
            <td data-group="leave" class="td-num">${e.open_el}</td>
            <td data-group="leave" class="td-num">${e.close_cl}</td>
            <td data-group="leave" class="td-num">${e.close_sl}</td>
            <td data-group="leave" class="td-num">${e.close_el}</td>

            <td data-group="salary" class="td-money td-num">${inr(e.standard_salary)}</td>
            <td data-group="salary" class="td-money td-num">${inr(e.current_salary)}</td>
            <td data-group="salary" class="td-money td-num ${e.bonus > 0 ? '' : 'td-zero'}">${e.bonus > 0 ? inr(e.bonus) : '—'}</td>
            <td data-group="salary" class="td-money td-num ${e.gratuity > 0 ? '' : 'td-zero'}" style="color:${e.gratuity>0?'#7c3aed':''}">${e.gratuity > 0 ? inr(e.gratuity) : '—'}</td>
            <td class="td-gross">${inr(e.final_gross)}</td>

            <td data-group="deductions" class="td-num">${inr(e.epf_employee)}</td>
            <td data-group="deductions" class="td-num">${inr(e.esi_employee)}</td>
            <td data-group="deductions" class="td-num ${e.profession_tax > 0 ? '' : 'td-zero'}">${e.profession_tax > 0 ? inr(e.profession_tax) : '—'}</td>
            <td data-group="deductions" class="td-editable-cell">
                <input type="number" class="manual-ded-inp" data-field="tds"       min="0" step="1" value="${tdsVal}" placeholder="0">
            </td>
            <td data-group="deductions" class="td-editable-cell">
                <input type="number" class="manual-ded-inp" data-field="insurance" min="0" step="1" value="${insVal}" placeholder="0">
            </td>
            <td data-group="deductions" class="td-editable-cell">
                <input type="number" class="manual-ded-inp" data-field="other"     min="0" step="1" value="${otherVal}" placeholder="0">
            </td>
            <td data-group="deductions" class="td-num td-total-ded" style="color:var(--red);font-weight:600">${inr(e.total_deductions)}</td>

            <td class="td-net">${inr(e.net_salary)}</td>

            <td data-group="employer" class="td-num">${inr(e.pension)}</td>
            <td data-group="employer" class="td-num">${inr(e.pf_employer)}</td>
            <td data-group="employer" class="td-num">${inr(e.esi_employer)}</td>
            <td data-group="employer" class="td-num" style="font-weight:700">${inr(e.total_employer)}</td>
        </tr>`);
    });

    /* Re-apply hidden groups to new td cells */
    Object.entries(Payroll.hiddenGroups).forEach(([group, hidden]) => {
        $(`#payrollTable td[data-group="${group}"]`).toggleClass('col-hidden', hidden);
    });

    $('#prRowCount').text(`Showing ${rows.length} of ${Payroll.allRows.length} employees`);
}

/* ── Manual deduction live recalculation ────────────────────────────── */
$(document).on('input change', '#payrollTbody .manual-ded-inp', function () {
    const $inp   = $(this);
    const $tr    = $inp.closest('tr');
    const empId  = $tr.data('emp');
    const field  = $inp.data('field');
    const val    = Math.max(0, parseFloat($inp.val()) || 0);

    /* Find the employee object in allRows and filtered */
    const emp = Payroll.allRows.find(r => r.emp_id === empId);
    if (!emp) return;
    emp[field] = val;

    /* Recalculate total deductions and net salary */
    const totalDed = emp.pf_esi_lwf_total + emp.profession_tax +
                     (emp.tds || 0) + (emp.insurance || 0) + (emp.other || 0);
    emp.total_deductions = totalDed;
    emp.net_salary = Math.round(emp.final_gross - totalDed);

    /* Update visible cells */
    $tr.find('.td-total-ded').text(inr(totalDed));
    $tr.find('.td-net').text(inr(emp.net_salary));

    /* Refresh KPIs with updated totals */
    renderPayrollKPIs(Payroll.allRows);
});

function zeroCell(v) { return v === 0 ? `<span class="td-zero">0</span>` : v; }

/* ── Formatting helpers ─────────────────────────────────────────── */
function inr(v) {
    if (v == null || isNaN(v)) return '—';
    return '₹' + parseFloat(v).toLocaleString('en-IN', {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
    });
}

function fmt(v) {
    return parseFloat(v).toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

/* ── Downloads ──────────────────────────────────────────────────── */
window.downloadPayroll = function () {
    /* Generate CSV client-side so manual TDS/Insurance/Other edits are included */
    const rows = Payroll.allRows;
    if (!rows || !rows.length) { alert('No payroll data to download.'); return; }

    const headers = [
        'emp_id','email','mobile','doj','doe','customer','project','status','slab',
        'present','wo','leaves','hfl','ml','ul','lop','payable_days',
        'open_cl','open_sl','open_el','close_cl','close_sl','close_el',
        'standard_salary','basic','hra','gross_salary','bonus','gratuity','final_gross',
        'gross_for_pf','epf_wages','epf_employee','esi_employee','profession_tax','lwf',
        'tds','insurance','other','pf_esi_lwf_total','total_deductions','net_salary',
        'pension','pf_employer','esi_employer','total_employer','completed_years'
    ];

    const escape = v => {
        const s = String(v ?? '');
        return s.includes(',') || s.includes('"') || s.includes('\n')
            ? `"${s.replace(/"/g, '""')}"` : s;
    };

    const lines = [headers.join(',')];
    rows.forEach(e => {
        const r = [
            e.emp_id, e.email, e.mobile, e.doj, e.doe, e.customer, e.project, e.status, e.slab,
            e.present, e.wo, e.leaves, e.hfl, e.ml, e.ul, e.lop, e.payable_days,
            e.open_cl, e.open_sl, e.open_el, e.close_cl, e.close_sl, e.close_el,
            e.standard_salary, e.basic, e.hra, e.gross_salary, e.bonus, e.gratuity, e.final_gross,
            e.gross_for_pf, e.epf_wages, e.epf_employee, e.esi_employee, e.profession_tax, e.lwf,
            e.tds || 0, e.insurance || 0, e.other || 0,
            e.pf_esi_lwf_total, e.total_deductions, e.net_salary,
            e.pension, e.pf_employer, e.esi_employer, e.total_employer, e.completed_years
        ];
        lines.push(r.map(escape).join(','));
    });

    const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'payroll_output.csv';
    a.click();
};

window.downloadLeaveBalance = function () {
    window.location.href = '/api/payroll/download/leave_balance';
};

/* ═══════════════════════════════════════════════════════════════════
   FORMULA CONFIG PANEL
   ═══════════════════════════════════════════════════════════════════ */
let _fcCurrentConfig = null;   // live copy from server
let _fcDefaultConfig = null;   // server defaults for comparison

/* ── Load config on payroll tab open ───────────────────────────── */
$(function () {
    // Load config whenever user clicks Payroll nav
    $('#navPayroll').on('click', function () {
        if (!_fcCurrentConfig) loadPayrollConfig();
    });
});

function loadPayrollConfig() {
    $.getJSON('/api/payroll/config')
        .done(function (cfg) {
            _fcCurrentConfig = cfg;
            populateFcPanel(cfg);
        })
        .fail(function () {
            console.warn('Could not load payroll config');
        });
}

/* ── Toggle panel visibility ────────────────────────────────────── */
window.toggleFcPanel = function (forceState) {
    const $panel = $('#fcPanel');
    const $btn   = $('.btn-formula-cfg');
    const isOpen = forceState !== undefined ? !forceState : $panel.is(':visible');

    if (isOpen) {
        $panel.slideUp(200);
        $btn.removeClass('active');
    } else {
        if (!_fcCurrentConfig) loadPayrollConfig();
        $panel.slideDown(200);
        $btn.addClass('active');
    }
};

/* ── Populate all form fields from config object ────────────────── */
function populateFcPanel(cfg) {
    const sl = cfg.salary_slabs || {};
    const ep = cfg.epf || {};
    const es = cfg.esi || {};
    const gr = cfg.gratuity || {};
    const la = cfg.leave_accrual || {};

    const setV = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };

    // Salary slabs
    setV('fc_anchor_std',       sl.anchor?.standard ?? 12360);
    setV('fc_anchor_basic_pct', sl.anchor?.basic_pct ?? 1.0);
    setV('fc_anchor_hra_pct',   sl.anchor?.hra_pct ?? 0.0);
    setV('fc_amia_std',         sl.amia?.standard ?? 17000);
    setV('fc_amia_basic_pct',   sl.amia?.basic_pct ?? 0.9);
    setV('fc_amia_hra_pct',     sl.amia?.hra_pct ?? 0.1);
    setV('fc_asset_std',        sl.asset?.standard ?? 17000);
    setV('fc_asset_basic_pct',  sl.asset?.basic_pct ?? 0.9);
    setV('fc_asset_hra_pct',    sl.asset?.hra_pct ?? 0.1);

    // EPF
    setV('fc_epf_ceiling',      ep.ceiling ?? 15000);
    setV('fc_epf_emp_rate',     ep.employee_rate ?? 0.12);
    setV('fc_epf_pension_rate', ep.pension_rate ?? 0.0833);

    // ESI
    setV('fc_esi_emp_rate',  es.employee_rate ?? 0.0075);
    setV('fc_esi_emp_rate2', es.employer_rate ?? 0.0325);
    setV('fc_esi_exempt',    es.exemption_threshold ?? 21000);

    // Gratuity & Bonus
    setV('fc_month_days',       cfg.month_days ?? 28);
    setV('fc_bonus_threshold',  cfg.bonus_threshold_days ?? 15);
    setV('fc_grat_min_years',   gr.min_years ?? 5);
    setV('fc_grat_divisor',     gr.divisor ?? 26);
    setV('fc_grat_multiplier',  gr.multiplier ?? 15);

    // Leave accrual
    setV('fc_accrual_cl',       la.cl ?? 0.5);
    setV('fc_accrual_sl',       la.sl ?? 0.5);
    setV('fc_accrual_el',       la.el ?? 1.0);
    setV('fc_accrual_extra_el', la.extra_el ?? 0.25);

    // LWF
    setV('fc_lwf', cfg.lwf ?? 0);

    // Profession Tax slabs
    renderPtaxSlabs(cfg.profession_tax_slabs || []);
}

/* ── Profession Tax slab renderer ──────────────────────────────── */
function renderPtaxSlabs(slabs) {
    const sorted = [...slabs].sort((a, b) => b.from_amount - a.from_amount);
    const $wrap = $('#fcPtaxSlabs').empty();
    sorted.forEach((slab, i) => {
        $wrap.append(`
        <div class="fc-ptax-slab-row" data-idx="${i}">
            <label class="fc-lbl">Gross (excl. gratuity) ≥ ₹</label>
            <input class="fc-ptax-inp" type="number" step="1" value="${slab.from_amount}"
                   data-field="from_amount" placeholder="e.g. 20001">
            <label class="fc-lbl" style="margin-left:10px">Tax ₹</label>
            <input class="fc-ptax-inp" type="number" step="1" value="${slab.tax_amount}"
                   data-field="tax_amount" placeholder="e.g. 200">
            <button class="fc-ptax-remove" onclick="removePtaxSlab(${i})" title="Remove slab">
                <i class="fa-solid fa-trash-can"></i>
            </button>
        </div>`);
    });
}

window.addPtaxSlab = function () {
    const slabs = collectPtaxSlabs();
    slabs.push({ from_amount: 0, tax_amount: 0 });
    renderPtaxSlabs(slabs);
};

window.removePtaxSlab = function (idx) {
    const slabs = collectPtaxSlabs();
    slabs.splice(idx, 1);
    renderPtaxSlabs(slabs);
};

function collectPtaxSlabs() {
    const slabs = [];
    $('#fcPtaxSlabs .fc-ptax-slab-row').each(function () {
        const from = parseFloat($(this).find('[data-field="from_amount"]').val()) || 0;
        const tax  = parseFloat($(this).find('[data-field="tax_amount"]').val())  || 0;
        slabs.push({ from_amount: from, tax_amount: tax });
    });
    return slabs;
}

/* ── Read all form fields → config dict ────────────────────────── */
function collectFcConfig() {
    const getV = (id, fallback = 0) => {
        const el = document.getElementById(id);
        return el ? parseFloat(el.value) || fallback : fallback;
    };

    return {
        month_days:           getV('fc_month_days', 28),
        bonus_threshold_days: getV('fc_bonus_threshold', 15),
        salary_slabs: {
            anchor: {
                label: 'Standard Anchor',
                standard:  getV('fc_anchor_std', 12360),
                basic_pct: getV('fc_anchor_basic_pct', 1.0),
                hra_pct:   getV('fc_anchor_hra_pct', 0.0),
            },
            amia: {
                label: 'AMIA / Maternity',
                standard:  getV('fc_amia_std', 17000),
                basic_pct: getV('fc_amia_basic_pct', 0.9),
                hra_pct:   getV('fc_amia_hra_pct', 0.1),
            },
            asset: {
                label: 'Asset',
                standard:  getV('fc_asset_std', 17000),
                basic_pct: getV('fc_asset_basic_pct', 0.9),
                hra_pct:   getV('fc_asset_hra_pct', 0.1),
            },
        },
        leave_accrual: {
            cl:       getV('fc_accrual_cl', 0.5),
            sl:       getV('fc_accrual_sl', 0.5),
            el:       getV('fc_accrual_el', 1.0),
            extra_el: getV('fc_accrual_extra_el', 0.25),
        },
        epf: {
            employee_rate: getV('fc_epf_emp_rate', 0.12),
            pension_rate:  getV('fc_epf_pension_rate', 0.0833),
            ceiling:       getV('fc_epf_ceiling', 15000),
        },
        esi: {
            employee_rate:        getV('fc_esi_emp_rate', 0.0075),
            employer_rate:        getV('fc_esi_emp_rate2', 0.0325),
            exemption_threshold:  getV('fc_esi_exempt', 21000),
        },
        profession_tax_slabs: collectPtaxSlabs(),
        lwf:      getV('fc_lwf', 0),
        gratuity: {
            min_years:   getV('fc_grat_min_years', 5),
            multiplier:  getV('fc_grat_multiplier', 15),
            divisor:     getV('fc_grat_divisor', 26),
        },
        slab_detection: _fcCurrentConfig?.slab_detection || {
            amia_keywords:  ['aima', 'amia'],
            asset_keywords: ['bht', 'asset'],
        },
    };
}

/* ── Save config ────────────────────────────────────────────────── */
window.savePayrollConfig = function () {
    const cfg = collectFcConfig();
    const $toast = $('#fcSaveToast');

    $.ajax({
        url: '/api/payroll/config',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(cfg),
        success: function (res) {
            _fcCurrentConfig = cfg;
            $toast.removeClass('error').addClass('success')
                  .html('<i class="fa-solid fa-circle-check"></i> ' + res.message)
                  .show();
            setTimeout(() => $toast.fadeOut(), 4000);
            $('#fcCustomBadge').show();
        },
        error: function (err) {
            const msg = err.responseJSON?.detail || 'Failed to save configuration.';
            $toast.removeClass('success').addClass('error')
                  .html('<i class="fa-solid fa-circle-xmark"></i> ' + msg)
                  .show();
            setTimeout(() => $toast.fadeOut(), 5000);
        }
    });
};

/* ── Reset to defaults ──────────────────────────────────────────── */
window.resetPayrollConfig = function () {
    if (!confirm('Reset all formula parameters to built-in defaults?')) return;
    $.ajax({
        url: '/api/payroll/config/reset',
        type: 'POST',
        success: function (res) {
            _fcCurrentConfig = res.config;
            populateFcPanel(res.config);
            $('#fcCustomBadge').hide();
            const $toast = $('#fcSaveToast');
            $toast.removeClass('error').addClass('success')
                  .html('<i class="fa-solid fa-rotate-left"></i> Reset to defaults.')
                  .show();
            setTimeout(() => $toast.fadeOut(), 3000);
        },
    });
};