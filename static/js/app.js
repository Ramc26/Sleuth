/**
 * Sleuth — App State & UI Controller  |  app.js v2.2
 * Two-tab: Data Entry (multi-PDF queue + viewer + editable) | Audit Suite
 * Health checks for Qdrant, clear error UX for failed investigations.
 */

/* ════════════════════════════════════════════════
   Health Check (Qdrant)
   ════════════════════════════════════════════════ */

/**
 * Called on page load and every 30 s.
 * Shows / hides the system warning banner based on Qdrant status.
 */
function checkHealth() {
    const $btn = $('#sysWarningRetry');
    $btn.prop('disabled', true).text('Checking…');

    $.getJSON('/api/health')
        .done(function (res) {
            if (res.ok) {
                // All good — hide the banner
                $('#sysWarning').fadeOut(300);
            } else if (!res.qdrant.reachable) {
                showWarning(
                    '🐳 Vector Store Offline',
                    res.qdrant.error || 'Qdrant is not reachable. Start Docker to enable forensic investigation.',
                    false   // amber (Docker down)
                );
            } else {
                showWarning(
                    '📭 Evidence Locker Empty',
                    res.qdrant.error || 'Click \'Sync Evidence Locker\' to index your evidence files into Qdrant.',
                    true    // blue (collection missing)
                );
            }
        })
        .fail(function () {
            showWarning(
                '⚠️ Health Check Failed',
                'Could not reach the Sleuth backend. Is Uvicorn running?',
                false
            );
        })
        .always(function () {
            $btn.prop('disabled', false).text('Retry');
        });
}

function showWarning(title, msg, isCollectionWarning) {
    const $banner = $('#sysWarning');
    $('#sysWarningTitle').text(title);
    $('#sysWarningMsg').text(msg);
    $banner
        .toggleClass('warn-collection', isCollectionWarning)
        .show();
}

/* ════════════════════════════════════════════════
   Global State
   ════════════════════════════════════════════════ */
const State = {
    queue: [],    // Array of File objects
    queueIndex: 0,     // Which file we're currently displaying/processing
    results: [],    // Extraction results per queued file: {file, status, data, pdfUrl}
    sessionHistory: [],   // Invoices saved this session
    activeRowId: null,  // Currently-investigated invoice_id in audit tab
};

/* ════════════════════════════════════════════════
   Tab Navigation
   ════════════════════════════════════════════════ */
function switchTab(tabKey) {
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
    document.getElementById(`tab-${tabKey}`).classList.add('active');
    const navMap = { 'data-entry': 'navDataEntry', 'audit-suite': 'navAuditSuite' };
    document.getElementById(navMap[tabKey]).classList.add('active');
}

/* ════════════════════════════════════════════════
   TAB 1 — Invoice Upload
   ════════════════════════════════════════════════ */
$(function () {

    // ── Health check on load + every 30 s ──────────────────────────
    checkHealth();
    setInterval(checkHealth, 30000);

    // ── Drag & Drop ────────────────────────────────────────────────
    const $dz = $('#invoiceDropzone');

    $dz.on('dragover dragenter', function (e) {
        e.preventDefault();
        $dz.addClass('dragover');
    }).on('dragleave drop', function (e) {
        e.preventDefault();
        $dz.removeClass('dragover');
        if (e.type === 'drop') {
            const files = Array.from(e.originalEvent.dataTransfer.files)
                .filter(f => f.name.toLowerCase().endsWith('.pdf'));
            if (files.length) startQueue(files);
            else showToast('❌ Please drop PDF files only.', 'error');
        }
    });

    $('#invoiceFileInput').on('change', function () {
        const files = Array.from(this.files);
        if (files.length) startQueue(files);
        this.value = '';
    });

    /* ── Queue Management ─────────────────────────────────────────── */
    function startQueue(files) {
        State.queue = files;
        State.queueIndex = 0;
        State.results = files.map(f => ({ file: f, status: 'pending', data: null, pdfUrl: null }));

        // Reset UI
        $('#reviewWorkspace').hide();
        $('#saveToast').hide();
        $('#processingCard').hide();

        renderQueueBar();
        processNext();
    }

    function renderQueueBar() {
        const total = State.queue.length;
        if (total <= 1) { $('#queueBar').hide(); return; }

        $('#queueBar').show();
        $('#queueTotal').text(total);
        $('#queueCurrent').text(State.queueIndex + 1);
        $('#queueFilename').text(State.queue[State.queueIndex]?.name || '');

        // Progress fill
        const pct = Math.round((State.queueIndex / total) * 100);
        $('#queueFill').css('width', pct + '%');

        // File chips
        const $chips = $('#queueFiles').empty();
        State.results.forEach((r, i) => {
            let cls = 'queue-file-chip';
            if (r.status === 'done') cls += ' done';
            if (r.status === 'error') cls += ' error';
            if (i === State.queueIndex && r.status === 'pending') cls += ' active';
            const icon = r.status === 'done' ? '✅' : r.status === 'error' ? '❌' : '📄';
            $chips.append(`<span class="${cls}">${icon} ${truncate(r.file.name, 18)}</span>`);
        });
    }

    function processNext() {
        if (State.queueIndex >= State.queue.length) {
            // All done — update progress bar to 100%
            $('#queueFill').css('width', '100%');
            renderQueueBar();
            return;
        }

        renderQueueBar();
        uploadFile(State.queue[State.queueIndex], State.queueIndex);
    }

    /* ── Upload & Extraction ──────────────────────────────────────── */
    function uploadFile(file, idx) {
        // Show skeleton
        $('#reviewWorkspace').hide();
        $('#processingCard').show();
        $('#processingLabel').text(`Extracting "${file.name}"… (${idx + 1}/${State.queue.length})`);

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

                $('#processingCard').hide();
                showReview(idx);
            },
            error: function (err) {
                State.results[idx].status = 'error';
                const detail = err.responseJSON ? err.responseJSON.detail : 'Extraction failed.';
                $('#processingCard').hide();
                showToast(`❌ "${file.name}" — ${detail}`, 'error');

                // Auto-advance to next file after a short delay
                setTimeout(() => {
                    State.queueIndex++;
                    processNext();
                }, 2500);
            },
            complete: function () {
                renderQueueBar();
            }
        });
    }

    /* ── Review Panel (PDF Viewer + Editable Fields) ─────────────── */
    function showReview(idx) {
        const result = State.results[idx];
        if (!result || result.status !== 'done') return;

        const d = result.data;
        const pdfUrl = result.pdfUrl;

        // PDF Viewer
        $('#pdfViewerFilename').text(result.file.name);
        $('#pdfEmbed').attr('src', pdfUrl);
        $('#pdfDownloadLink').attr('href', pdfUrl);
        $('#pdfFallback').hide();
        $('#pdfEmbed').show();

        // Editable fields
        $('#extInvoiceId').val(d.invoice_id || '');
        $('#extEntity').val(d.entity || '');
        $('#extAmount').val(d.amount != null ? parseFloat(d.amount).toFixed(2) : '');
        $('#extDate').val(d.date || '');

        // Enable/reset action buttons
        $('#confirmSaveBtn').prop('disabled', false).html('💾 Confirm & Save to Ledger');
        $('#reExtractBtn').prop('disabled', false).html('🔄 Re-extract');

        $('#reviewWorkspace').show();
    }

    /* ── Re-extract ─────────────────────────────────────────────── */
    $('#reExtractBtn').on('click', function () {
        const idx = State.queueIndex;
        const file = State.queue[idx];
        if (!file) return;

        $(this).prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span>');
        State.results[idx].status = 'pending';
        uploadFile(file, idx);
    });

    /* ── Confirm Save ──────────────────────────────────────────── */
    $('#confirmSaveBtn').on('click', function () {
        const idx = State.queueIndex;
        const result = State.results[idx];
        if (!result) return;

        // Read the (possibly edited) field values back
        const saved = {
            invoice_id: $('#extInvoiceId').val().trim(),
            entity: $('#extEntity').val().trim(),
            amount: parseFloat($('#extAmount').val()) || 0,
            date: $('#extDate').val().trim(),
        };

        $(this).prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Saving…');

        // Note: the data was already appended to CSV on the server during extraction.
        // Here we just acknowledge the save and advance the queue.
        // (If edits were made, a future enhancement would re-submit them.
        //  For now the server already wrote the original extracted JSON.)
        addToHistory(saved, result.file.name);
        showToast(`✅ Invoice ${saved.invoice_id} (${saved.entity}) confirmed.`, 'success');

        // Advance to next file
        State.queueIndex++;
        if (State.queueIndex < State.queue.length) {
            setTimeout(() => {
                $('#reviewWorkspace').hide();
                processNext();
            }, 800);
        } else {
            // All done
            $('#reviewWorkspace').hide();
            renderQueueBar();
        }
    });

    /* ── Discard ─────────────────────────────────────────────────── */
    $('#discardBtn').on('click', function () {
        $('#reviewWorkspace').hide();
        showToast('↩️ Invoice discarded.', 'error');

        State.queueIndex++;
        if (State.queueIndex < State.queue.length) {
            setTimeout(() => processNext(), 600);
        } else {
            renderQueueBar();
        }
    });

    /* ── History ─────────────────────────────────────────────────── */
    function addToHistory(d, filename) {
        State.sessionHistory.unshift({ ...d, filename });
        if (State.sessionHistory.length > 5) State.sessionHistory.pop();

        const $list = $('#historyList').empty();
        State.sessionHistory.forEach(item => {
            $list.append(`
                <li class="history-item">
                    <div>
                        <span class="history-inv">${item.invoice_id || '—'}</span>
                        <span class="history-meta"> · ${item.entity || '—'} · ${item.date || '—'}</span>
                    </div>
                    <span class="history-amt">$${parseFloat(item.amount || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                </li>
            `);
        });
        $('#historyCard').show();
    }

    /* ── Toast ───────────────────────────────────────────────────── */
    function showToast(message, type) {
        const $t = $('#saveToast');
        $t.removeClass('success error').addClass(type).text(message).show();
        setTimeout(() => $t.fadeOut(), 4500);
    }

    /* ── Utility ─────────────────────────────────────────────────── */
    function truncate(str, len) {
        return str.length > len ? str.slice(0, len) + '…' : str;
    }

    /* ════════════════════════════════════════════════
       TAB 2 — Reconciliation
       ════════════════════════════════════════════════ */

    // ── Reconcile Form ─────────────────────────────────────────────
    $('#reconcileForm').on('submit', function (e) {
        e.preventDefault();
        const fileA = $('#fileA')[0].files[0];
        const fileB = $('#fileB')[0].files[0];
        if (!fileA || !fileB) return;

        const formData = new FormData();
        formData.append('file_a', fileA);
        formData.append('file_b', fileB);

        const $btn = $('#reconcileBtn');
        $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Reconciling…');
        $('#boardTbody').html('<tr><td colspan="5" class="empty-state"><div class="spinner-border text-secondary"></div><br>Merging ledgers…</td></tr>');
        $('#reportContainer').html('<div class="report-empty"><div class="report-empty-icon" style="opacity:.15">⚖️</div><p>Run reconciliation to begin.</p></div>');
        resetReportBadge();

        $.ajax({
            url: '/api/reconcile',
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function (res) {
                updateKPIs(res.summary);
                renderBoard(res.data);
            },
            error: function (err) {
                const detail = err.responseJSON ? err.responseJSON.detail : 'Reconciliation failed.';
                $('#boardTbody').html(`<tr><td colspan="5" class="empty-state" style="color:var(--red)">❌ ${detail}</td></tr>`);
            },
            complete: function () {
                $btn.prop('disabled', false).html('⚖️ Reconcile');
            }
        });
    });

    function updateKPIs(summary) {
        $('#metricTotal').text(summary.total_rows);
        $('#metricFlagged').text(summary.flagged);
        $('#metricRisk').text('$' + parseFloat(summary.risk).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
    }

    function renderBoard(rows) {
        const $tbody = $('#boardTbody').empty();
        const discrepancies = rows.filter(r => r.status === 'Discrepancy');
        const matched = rows.filter(r => r.status === 'Matched');
        const ordered = [...discrepancies, ...matched];

        if (ordered.length === 0) {
            $tbody.html('<tr><td colspan="5" class="empty-state">No matching rows found after merge.</td></tr>');
            $('#boardCount').text('');
            return;
        }

        $('#boardCount').text(`${discrepancies.length} flagged of ${rows.length}`);

        ordered.forEach(row => {
            const isDiscrepancy = row.status === 'Discrepancy';
            const badge = isDiscrepancy
                ? '<span class="status-badge badge-discrepancy">🔴 Discrepancy</span>'
                : '<span class="status-badge badge-matched">🟢 Matched</span>';

            const varianceClass = isDiscrepancy ? 'variance-red' : 'variance-zero';
            const varianceText = isDiscrepancy ? `$${parseFloat(row.Variance).toFixed(2)}` : '—';

            const investigateBtn = isDiscrepancy
                ? `<button class="btn-investigate"
                        data-inv="${row.invoice_id}"
                        data-ent="${row.entity}"
                        data-amta="${row.amount_SubA}"
                        data-amtb="${row.amount_SubB}">
                        Investigate
                   </button>`
                : '';

            $tbody.append(`
                <tr id="row-${row.invoice_id}">
                    <td><strong>${row.invoice_id}</strong></td>
                    <td>${row.entity}</td>
                    <td>${badge}</td>
                    <td class="${varianceClass}">${varianceText}</td>
                    <td>${investigateBtn}</td>
                </tr>
            `);
        });
    }

    // ── Investigation Click ────────────────────────────────────────
    $(document).on('click', '.btn-investigate', function () {
        const $btn = $(this);
        const inv_id = $btn.data('inv');
        const entity = $btn.data('ent');
        const amt_a = parseFloat($btn.data('amta'));
        const amt_b = parseFloat($btn.data('amtb'));

        if (State.activeRowId === inv_id) return;
        State.activeRowId = inv_id;

        $('#boardTbody tr').removeClass('active-row');
        $(`#row-${inv_id}`).addClass('active-row');
        $('.btn-investigate').prop('disabled', true);
        $btn.html('<span class="spinner-border spinner-border-sm"></span>');

        const $badge = $('#investigationStatus');
        $badge.text(`Investigating ${inv_id}…`)
            .removeClass('status-resolved status-error')
            .addClass('status-investigating');

        $('#reportContainer').html(`
            <div class="report-empty">
                <div class="spinner-border text-primary mb-3" style="width:28px;height:28px;border-width:3px"></div>
                <p style="font-weight:600;color:var(--text-primary)">Sleuth is analyzing…</p>
                <p style="font-size:12px">Querying Qdrant · Generating Audit Report</p>
            </div>
        `);

        $.ajax({
            url: '/api/investigate',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ invoice_id: inv_id, entity, amount_a: amt_a, amount_b: amt_b }),
            success: function (res) {
                $('#reportContainer').html(marked.parse(res.report));
                $badge.text('Resolved').removeClass('status-investigating').addClass('status-resolved');
            },
            error: function (err) {
                // Surface the specific server error message
                const detail = err.responseJSON ? err.responseJSON.detail : null;
                const statusCode = err.status;

                let icon = '⚠️';
                let heading = 'Investigation Failed';
                let hint = '';

                if (statusCode === 503) {
                    // Structured messages from our pre-flight check
                    icon = detail && detail.includes('🐳') ? '🐳' : '📭';
                    heading = detail && detail.includes('Offline') ? 'Vector Store Offline'
                        : detail && detail.includes('Empty') ? 'Evidence Locker Empty'
                            : 'Service Unavailable';
                    hint = '<br><small style="opacity:.7">Run <code>docker run -p 6333:6333 qdrant/qdrant</code> then click \"Sync Evidence Locker\".</small>';
                }

                const displayMsg = detail || 'An unexpected error occurred during investigation.';

                $('#reportContainer').html(`
                    <div style="padding:24px">
                        <div style="font-size:32px;margin-bottom:12px">${icon}</div>
                        <p style="font-weight:700;font-size:15px;color:#0f172a;margin-bottom:8px">${heading}</p>
                        <p style="font-size:13px;color:#64748b;line-height:1.65;margin-bottom:0">${displayMsg}${hint}</p>
                    </div>
                `);
                $badge.text('Error').removeClass('status-investigating').addClass('status-error');

                // If Qdrant is down, refresh the banner
                if (statusCode === 503) checkHealth();
            },
            complete: function () {
                $btn.html('Investigate').prop('disabled', false);
                $('.btn-investigate').prop('disabled', false);
                State.activeRowId = null;
            }
        });
    });

    function resetReportBadge() {
        $('#investigationStatus')
            .text('Awaiting Selection')
            .removeClass('status-investigating status-resolved status-error');
    }

    /* ════════════════════════════════════════════════
       Evidence Sync
       ════════════════════════════════════════════════ */
    $('#indexDbBtn').on('click', function () {
        const $btn = $(this);
        $btn.prop('disabled', true);
        $('#syncBtnText').text('Syncing…');

        $.post('/api/index_db')
            .done(() => $('#syncBtnText').text('✅ Synced!'))
            .fail(() => $('#syncBtnText').text('❌ Sync Failed'))
            .always(() => {
                $btn.prop('disabled', false);
                setTimeout(() => $('#syncBtnText').text('Sync Evidence Locker'), 3000);
            });
    });

});