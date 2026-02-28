$(document).ready(function() {
    
    // 1. Handle File Uploads & Reconciliation
    $("#uploadForm").submit(function(e) {
        e.preventDefault();
        
        let fileA = $("#fileA")[0].files[0];
        let fileB = $("#fileB")[0].files[0];
        
        if (!fileA || !fileB) return;

        let formData = new FormData();
        formData.append("file_a", fileA);
        formData.append("file_b", fileB);

        // Reset UI
        $("#discrepancyTable tbody").html('<tr><td colspan="4" class="text-center py-4"><div class="spinner-border text-primary" role="status"></div><br>Reconciling...</td></tr>');
        
        $.ajax({
            url: "/api/reconcile",
            type: "POST",
            data: formData,
            processData: false,
            contentType: false,
            success: function(response) {
                // Update Metrics
                $("#metricTotal").text(response.summary.total_rows);
                $("#metricFlagged").text(response.summary.flagged);
                $("#metricRisk").text("$" + response.summary.risk.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2}));

                let tbody = $("#discrepancyTable tbody");
                tbody.empty();
                
                if(response.data.length === 0) {
                    tbody.append('<tr><td colspan="4" class="text-center text-success py-4">All ledgers match perfectly!</td></tr>');
                    return;
                }

                // Render Table
                response.data.forEach(row => {
                    let tr = `
                        <tr>
                            <td><strong>${row.invoice_id}</strong></td>
                            <td class="text-muted">${row.entity}</td>
                            <td class="variance-cell">$${row.Variance.toFixed(2)}</td>
                            <td>
                                <button class="btn btn-sm btn-outline-primary investigate-btn rounded-pill px-3" 
                                    data-inv="${row.invoice_id}" 
                                    data-ent="${row.entity}"
                                    data-amta="${row.amount_SubA}"
                                    data-amtb="${row.amount_SubB}">
                                    Investigate
                                </button>
                            </td>
                        </tr>
                    `;
                    tbody.append(tr);
                });
            },
            error: function(err) {
                alert(err.responseJSON ? err.responseJSON.detail : "Error uploading files.");
                $("#discrepancyTable tbody").html('<tr><td colspan="4" class="text-center py-4 text-danger">Upload Failed.</td></tr>');
            }
        });
    });

    // 2. Handle Investigation Click
    $(document).on("click", ".investigate-btn", function() {
        let btn = $(this);
        let inv_id = btn.data("inv");
        
        // UI Loading State
        $(".investigate-btn").removeClass("btn-primary").addClass("btn-outline-primary").prop("disabled", true);
        btn.removeClass("btn-outline-primary").addClass("btn-primary");
        btn.html('<span class="spinner-border spinner-border-sm"></span>');
        
        $("#investigationStatus").removeClass("bg-secondary bg-success bg-danger").addClass("bg-warning text-dark").text("Investigating " + inv_id + "...");
        $("#reportContainer").html(`
            <div class="text-center py-5">
                <div class="spinner-grow text-primary" role="status"></div>
                <h6 class="mt-3 fw-bold">Sleuth is analyzing context...</h6>
                <p class="text-muted small">Querying Qdrant Vector DB & OpenAI</p>
            </div>
        `);

        let payload = {
            invoice_id: inv_id,
            entity: btn.data("ent"),
            amount_a: parseFloat(btn.data("amta")),
            amount_b: parseFloat(btn.data("amtb"))
        };

        $.ajax({
            url: "/api/investigate",
            type: "POST",
            contentType: "application/json",
            data: JSON.stringify(payload),
            success: function(response) {
                // Parse markdown to HTML
                $("#reportContainer").html(marked.parse(response.report));
                $("#investigationStatus").removeClass("bg-warning text-dark").addClass("bg-success text-white").text("Resolved");
            },
            error: function() {
                $("#reportContainer").html('<p class="text-danger fw-bold">Error generating report.</p>');
                $("#investigationStatus").removeClass("bg-warning text-dark").addClass("bg-danger text-white").text("Error");
            },
            complete: function() {
                btn.html("Investigate").prop("disabled", false);
                $(".investigate-btn").prop("disabled", false);
            }
        });
    });

    // 3. Handle Database Indexing
    $("#indexDbBtn").click(function() {
        let btn = $(this);
        let originalText = btn.text();
        btn.prop("disabled", true).html('<span class="spinner-border spinner-border-sm"></span> Syncing...');
        
        $.post("/api/index_db", function(res) {
            alert("✅ " + res.message);
        }).fail(function() {
            alert("❌ Error indexing database.");
        }).always(function() {
            btn.prop("disabled", false).html(originalText);
        });
    });
});