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
    const navMap = { capture: 'navDataEntry', analysis: 'navAuditSuite' };
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