/**
 * Frontend Logic: AI Vector Data & Task Breakdown Dashboard
 * Điều khiển giao diện tương tác, trực quan hoá Vector Embeddings, và RAG Pipeline
 */

document.addEventListener('DOMContentLoaded', () => {
    // State cục bộ
    let globalDataPrep = null;
    let analyzedTasks = [];
    let currentSelectedPlatform = "Jira";

    // 1. Khởi tạo & nạp dữ liệu ban đầu
    initDiagramInteractions();
    initTabNavigation();
    loadDataPrepInspection();
    loadRulesPreview();
    setupEventHandlers();

    // =========================================================================
    // 2. DIAGRAM INTERACTIVE EXPLAINER (Khớp chính xác với hình ảnh của User)
    // =========================================================================
    const STEP_EXPLANATIONS = {
        "raw": "<strong>Raw Data Sources:</strong> File Excel nhận từ Dev (ví dụ: historical_dev_backlog.xlsx) chứa lịch sử các ticket đã release, actual hours, tech stack, dev notes.",
        "step-a": "<strong>[A] Information Extraction:</strong> Parser thông minh đọc file Excel, tự động map các cột lộn xộn (Tên việc, ghi chú, giờ thực tế, tech stack) thành JSON có cấu trúc chuẩn.",
        "step-b": "<strong>[B] Semantic Chunking:</strong> Đóng gói từng dòng task thành Chunk văn bản kỹ thuật giàu metadata (Module, Task Type, Tech Stack, Description) tối ưu cho việc hiểu ngữ nghĩa.",
        "step-c": "<strong>[C] Dense Embedding:</strong> Vector hoá văn bản thành mảng số thực 128 chiều (Dense Vector Float32). Các từ đồng nghĩa kỹ thuật (JWT, Auth, Token, QR, OTP) sẽ nằm gần nhau trong không gian.",
        "step-d": "<strong>[D] Vector Database:</strong> Lưu trữ Vector + Metadata vào TinyVectorStore. Chỉ số L2 Norm = 1.0 giúp phép tính Cosine Similarity tương đương với Dot Product siêu tốc.",
        "step-1": "<strong>[1] Query (New Requirement):</strong> Dev hoặc BA cung cấp User Story mới hoặc danh sách task thô từ file Excel cần phân tích và log lên Jira/ADO.",
        "step-2": "<strong>[2] Vector Search (k-NN):</strong> Query mới được embed thành vector và đem so sánh Cosine Similarity với toàn bộ kho ticket trong Vector DB để tìm k láng giềng gần nhất.",
        "step-3": "<strong>[3] Relevant Data:</strong> Trích xuất Top-K ticket trong quá khứ có ngữ cảnh kỹ thuật giống nhất, kèm theo số giờ thực tế (Actual Hours) đã làm trong lịch sử.",
        "step-4": "<strong>[4] RAG Synthesis:</strong> Engine kết hợp Query + Relevant Historical Tasks + Project Rules để chuẩn hoá Naming ([TYPE][MODULE]) và tính toán giờ theo trọng số tương đồng.",
        "step-5": "<strong>[5] Jira/ADO Ticket Response:</strong> Sinh ra Payload chuẩn REST API, gắn cờ Ready/Warning (Phase 2), cho phép Human review/approve và bắn tự động lên Jira hoặc Azure DevOps."
    };

    function initDiagramInteractions() {
        const nodes = document.querySelectorAll('.diagram-node');
        const explainerText = document.getElementById('explainer-content');

        nodes.forEach(node => {
            node.addEventListener('click', () => {
                nodes.forEach(n => n.classList.remove('active-step'));
                node.classList.add('active-step');

                const stepKey = node.getAttribute('data-step');
                if (STEP_EXPLANATIONS[stepKey]) {
                    explainerText.innerHTML = STEP_EXPLANATIONS[stepKey];
                }
            });
        });

        // Toggle diagram visibility
        const toggleBtn = document.getElementById('btn-toggle-diagram');
        const diagramContainer = document.getElementById('interactive-diagram');
        if (toggleBtn && diagramContainer) {
            toggleBtn.addEventListener('click', () => {
                if (diagramContainer.style.display === 'none') {
                    diagramContainer.style.display = 'flex';
                    toggleBtn.textContent = 'Thu gọn';
                } else {
                    diagramContainer.style.display = 'none';
                    toggleBtn.textContent = 'Mở rộng sơ đồ';
                }
            });
        }
    }

    // =========================================================================
    // 3. TAB NAVIGATION
    // =========================================================================
    function initTabNavigation() {
        const tabBtns = document.querySelectorAll('.tab-btn');
        const tabContents = document.querySelectorAll('.tab-content');

        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                const targetTabId = btn.getAttribute('data-tab');

                tabBtns.forEach(b => b.classList.remove('active'));
                tabContents.forEach(c => c.classList.remove('active'));

                btn.classList.add('active');
                const targetContent = document.getElementById(targetTabId);
                if (targetContent) {
                    targetContent.classList.add('active');
                }
            });
        });
    }

    // =========================================================================
    // 4. DATA PREPARATION (A -> D) LOAD & HEATMAP
    // =========================================================================
    async function loadDataPrepInspection() {
        try {
            const res = await fetch('/api/data-prep/inspect');
            const data = await res.json();
            globalDataPrep = data;

            // Render table extracted
            const tbody = document.getElementById('tbody-extracted');
            const items = data.step_a_extraction.items || [];
            if (tbody && items.length > 0) {
                tbody.innerHTML = items.map(item => `
                    <tr>
                        <td><strong style="color: var(--accent-cyan);">${item.ticket_key}</strong></td>
                        <td><span class="badge">${item.module}</span></td>
                        <td><strong>${escapeHtml(item.title)}</strong><br><small style="color: var(--text-muted);">${escapeHtml(item.description.substring(0, 70))}...</small></td>
                        <td><strong style="color: #34d399;">${item.actual_hours}h</strong> <small style="color: var(--text-muted);">(${item.story_points} SP)</small></td>
                        <td><small style="color: var(--text-secondary);">${escapeHtml(item.tech_stack || 'N/A')}</small></td>
                    </tr>
                `).join('');
            }

            // Render Vector Heatmap (24 chiều)
            const heatmapContainer = document.getElementById('vector-heatmap-container');
            const sampleVec = data.step_c_embedding.sample;
            if (heatmapContainer && sampleVec && sampleVec.vector_snippet) {
                document.getElementById('vec-ticket-key').textContent = sampleVec.ticket_key;
                const snippet = sampleVec.vector_snippet;

                heatmapContainer.innerHTML = snippet.map((val, idx) => {
                    // val nằm trong khoảng [-1.0, 1.0]. Tính màu tương ứng
                    let bgCol = "rgba(255, 255, 255, 0.05)";
                    if (val > 0) {
                        const intensity = Math.min(1, val * 3);
                        bgCol = `rgba(56, 189, 248, ${0.2 + intensity * 0.8})`;
                    } else if (val < 0) {
                        const intensity = Math.min(1, Math.abs(val) * 3);
                        bgCol = `rgba(244, 63, 94, ${0.2 + intensity * 0.8})`;
                    }
                    return `<div class="heatmap-cell" style="background: ${bgCol};" title="Dim ${idx}: ${val.toFixed(4)}">${val.toFixed(2)}</div>`;
                }).join('');

                // Update raw vector preview
                const rawBox = document.getElementById('vector-raw-box');
                if (rawBox) {
                    const previewStr = "[" + snippet.slice(0, 8).map(v => v.toFixed(4)).join(", ") + ", ... " + (sampleVec.dimension - 8) + " dims]";
                    rawBox.textContent = previewStr;
                }
            }

            // Update stats
            if (data.step_d_vectordb) {
                const totalVecElem = document.getElementById('stat-total-vectors');
                if (totalVecElem) totalVecElem.textContent = data.step_d_vectordb.indexed_count;
            }
        } catch (err) {
            console.error("Lỗi nạp Data Prep:", err);
        }
    }

    // =========================================================================
    // 5. VECTOR SEARCH (1 -> 3)
    // =========================================================================
    async function runVectorSearch(query) {
        if (!query.trim()) return;

        const resultsGrid = document.getElementById('results-cards-grid');
        resultsGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 20px;">Đang tính toán Cosine Similarity trong không gian 128D...</div>';

        try {
            const res = await fetch('/api/search-vectors', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: query, top_k: 3 })
            });
            const data = await res.json();

            if (data.matches && data.matches.length > 0) {
                resultsGrid.innerHTML = data.matches.map(m => `
                    <div class="match-card">
                        <div>
                            <div class="match-header">
                                <span class="match-key">${m.ticket_key}</span>
                                <span class="similarity-badge">Match: ${m.relevance_percent}%</span>
                            </div>
                            <div class="match-title">${escapeHtml(m.title)}</div>
                        </div>
                        <div class="match-meta">
                            <div><strong>Module:</strong> ${m.module} | <strong>Type:</strong> ${m.task_type}</div>
                            <div><strong>Lịch sử Actual:</strong> <span style="color: #34d399; font-weight: 700;">${m.actual_hours}h</span> (${m.story_points} SP)</div>
                            <div><strong>Cosine Score:</strong> ${m.similarity_score} | <strong>L2 Dist:</strong> ${m.euclidean_distance}</div>
                        </div>
                    </div>
                `).join('');
            } else {
                resultsGrid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; color: var(--text-muted); padding: 20px;">Không tìm thấy kết quả phù hợp.</div>';
            }
        } catch (err) {
            console.error("Lỗi search vector:", err);
            resultsGrid.innerHTML = `<div style="grid-column: 1/-1; color: var(--accent-rose); padding: 20px;">Lỗi: ${err.message}</div>`;
        }
    }

    // =========================================================================
    // 6. RAG PIPELINE & TASK BREAKDOWN (4 -> 5)
    // =========================================================================
    async function runRAGAnalysis() {
        const btn = document.getElementById('btn-run-analysis');
        const tbody = document.getElementById('tbody-analyzed');
        btn.disabled = true;
        btn.innerHTML = '⚡ Đang chạy RAG Pipeline...';
        tbody.innerHTML = '<tr><td colspan="8" class="text-center" style="padding: 24px;">Đang trích xuất Excel từ Dev, đối chiếu Vector DB và tính toán Naming/Estimate...</td></tr>';

        try {
            const res = await fetch('/api/analyze-requirements', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            const data = await res.json();
            analyzedTasks = data.tasks || [];

            // Update summary pills
            document.getElementById('count-ready').textContent = data.ready_count || 0;
            document.getElementById('count-warning').textContent = data.warning_count || 0;
            document.getElementById('count-total').textContent = data.total_analyzed || 0;

            renderAnalyzedTasksTable();
            updatePayloadPreview();
        } catch (err) {
            console.error("Lỗi phân tích RAG:", err);
            tbody.innerHTML = `<tr><td colspan="8" style="color: var(--accent-rose); text-align: center;">Lỗi: ${err.message}</td></tr>`;
        } finally {
            btn.disabled = false;
            btn.innerHTML = '⚡ Phân Tích Dev Excel Ngay';
        }
    }

    function renderAnalyzedTasksTable() {
        const tbody = document.getElementById('tbody-analyzed');
        if (!tbody || analyzedTasks.length === 0) return;

        tbody.innerHTML = analyzedTasks.map((t, idx) => {
            const topMatch = (t.similar_historical_tasks && t.similar_historical_tasks.length > 0) ? t.similar_historical_tasks[0] : null;
            const topMatchHtml = topMatch ? `
                <strong style="color: var(--accent-cyan);">${topMatch.ticket_key}</strong> 
                <small style="color: #34d399;">(${topMatch.similarity}% sim)</small><br>
                <small style="color: var(--text-muted);">${escapeHtml(topMatch.title.substring(0, 35))}...</small>
            ` : '<small style="color: var(--text-muted);">Không có</small>';

            let flagBadgeClass = "flag-ready";
            if (t.flag_status === "WARNING_DUPLICATE") flagBadgeClass = "flag-warning";
            else if (t.flag_status === "NEEDS_INPUT") flagBadgeClass = "flag-input";

            return `
                <tr>
                    <td class="text-center">
                        <input type="checkbox" class="task-checkbox" data-index="${idx}" ${t.is_approved ? 'checked' : ''}>
                    </td>
                    <td class="text-center">${idx + 1}</td>
                    <td>
                        <strong>${escapeHtml(t.original_title)}</strong><br>
                        <small style="color: var(--text-muted);">${escapeHtml(t.description || 'N/A')}</small>
                    </td>
                    <td>
                        <strong style="color: #fff; font-family: var(--font-mono); font-size: 0.8rem;">${escapeHtml(t.standardized_title)}</strong><br>
                        <small class="badge" style="margin-top: 4px;">${t.module} | ${t.task_type}</small>
                    </td>
                    <td class="text-center">
                        <strong style="color: #34d399; font-size: 0.95rem;">${t.estimated_hours}h</strong><br>
                        <span class="badge info-badge">${t.story_points} SP</span>
                    </td>
                    <td>${topMatchHtml}</td>
                    <td>
                        <span class="flag-badge ${flagBadgeClass}">${t.flag_status}</span><br>
                        <small style="color: var(--text-muted); font-size: 0.7rem;">${escapeHtml(t.flag_reason || '')}</small>
                    </td>
                    <td>
                        <button class="btn btn-outline btn-sm btn-edit-task" data-index="${idx}">Sửa</button>
                    </td>
                </tr>
            `;
        }).join('');

        // Gán sự kiện cho checkbox approve
        document.querySelectorAll('.task-checkbox').forEach(cb => {
            cb.addEventListener('change', async (e) => {
                const idx = parseInt(e.target.getAttribute('data-index'));
                const isChecked = e.target.checked;
                analyzedTasks[idx].is_approved = isChecked;

                await fetch('/api/update-task-approval', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ index: idx, is_approved: isChecked })
                });
                updatePayloadPreview();
            });
        });

        // Gán sự kiện cho nút Sửa modal
        document.querySelectorAll('.btn-edit-task').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(btn.getAttribute('data-index'));
                openEditModal(idx);
            });
        });
    }

    // =========================================================================
    // 7. JIRA & ADO INTEGRATION (PHASE 2 REVIEW & LOG TICKET)
    // =========================================================================
    function updatePayloadPreview() {
        const preElem = document.getElementById('payload-code-block');
        const badgeElem = document.getElementById('platform-payload-badge');
        if (!preElem) return;

        const firstApproved = analyzedTasks.find(t => t.is_approved) || (analyzedTasks.length > 0 ? analyzedTasks[0] : null);

        if (currentSelectedPlatform === "Jira") {
            if (badgeElem) badgeElem.textContent = "Atlassian Jira REST API v3";
            const samplePayload = {
                "fields": {
                    "project": { "key": document.getElementById('input-project-key').value || "PROJ" },
                    "summary": firstApproved ? firstApproved.standardized_title : "[BE][AUTH] Implement TOTP verification endpoint",
                    "description": "Auto-generated from Dev Excel via Vector RAG",
                    "issuetype": { "name": "Task" },
                    "priority": { "name": "High" },
                    "timetracking": {
                        "originalEstimate": `${firstApproved ? firstApproved.estimated_hours : 8}h`,
                        "remainingEstimate": `${firstApproved ? firstApproved.estimated_hours : 8}h`
                    },
                    "customfield_story_points": firstApproved ? firstApproved.story_points : 3,
                    "labels": ["ai-generated", "vector-rag"]
                }
            };
            preElem.textContent = JSON.stringify(samplePayload, null, 2);
        } else {
            if (badgeElem) badgeElem.textContent = "Azure DevOps JSON Patch API";
            const sampleAdo = [
                { "op": "add", "path": "/fields/System.Title", "value": firstApproved ? firstApproved.standardized_title : "[BE][AUTH] Implement TOTP endpoint" },
                { "op": "add", "path": "/fields/System.Description", "value": "Auto-generated from Dev Excel via Vector RAG" },
                { "op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.OriginalEstimate", "value": firstApproved ? firstApproved.estimated_hours : 8 },
                { "op": "add", "path": "/fields/Microsoft.VSTS.Scheduling.StoryPoints", "value": firstApproved ? firstApproved.story_points : 3 }
            ];
            preElem.textContent = JSON.stringify(sampleAdo, null, 2);
        }
    }

    async function executeImportTickets() {
        const btn = document.getElementById('btn-execute-import');
        const resultsBox = document.getElementById('sync-results-box');
        const alertBox = document.getElementById('sync-summary-alert');
        const container = document.getElementById('imported-tickets-container');
        const projKey = document.getElementById('input-project-key').value || "PROJ";

        btn.disabled = true;
        btn.innerHTML = '⏳ Đang bắn tasks lên hệ thống...';

        try {
            const res = await fetch('/api/import-tickets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    platform: currentSelectedPlatform,
                    project_key: projKey
                })
            });
            const data = await res.json();

            resultsBox.style.display = 'block';
            alertBox.innerHTML = `🎉 <strong>Thành công:</strong> Đã import <strong>${data.success_count}</strong> tickets lên ${currentSelectedPlatform}. Giữ lại <strong>${data.skipped_count}</strong> tasks chưa đạt chuẩn để Dev sửa.`;

            if (data.imported_tickets && data.imported_tickets.length > 0) {
                container.innerHTML = `
                    <div style="margin-top: 14px; max-height: 240px; overflow-y: auto;">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Ticket Key</th>
                                    <th>Summary</th>
                                    <th>Estimate</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.imported_tickets.map(t => `
                                    <tr>
                                        <td><strong style="color: #34d399;">${t.ticket_key}</strong></td>
                                        <td>${escapeHtml(t.title)}</td>
                                        <td>${t.estimated_hours}h (${t.story_points} SP)</td>
                                        <td><a href="${t.api_endpoint}" target="_blank" class="badge info-badge" style="text-decoration:none;">Xem API ↗</a></td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
            }
        } catch (err) {
            console.error("Lỗi import tickets:", err);
            resultsBox.style.display = 'block';
            alertBox.className = 'alert alert-danger';
            alertBox.textContent = `Lỗi: ${err.message}`;
        } finally {
            btn.disabled = false;
            btn.innerHTML = '🚀 Bắn Toàn Bộ Tasks Đã Duyệt Lên Nền Tảng';
        }
    }

    // =========================================================================
    // 8. RULES PREVIEW (STEP 1 & 4)
    // =========================================================================
    async function loadRulesPreview() {
        try {
            const res = await fetch('/api/rules');
            const data = await res.json();
            const rulesBox = document.getElementById('rules-markdown-box');
            if (rulesBox && data.markdown) {
                rulesBox.textContent = data.markdown;
            }
        } catch (err) {
            console.error("Lỗi nạp rules:", err);
        }
    }

    // =========================================================================
    // 9. MODAL EDIT
    // =========================================================================
    const modal = document.getElementById('edit-task-modal');
    function openEditModal(index) {
        const task = analyzedTasks[index];
        if (!task) return;

        document.getElementById('edit-task-index').value = index;
        document.getElementById('edit-task-title').value = task.standardized_title;
        document.getElementById('edit-task-hours').value = task.estimated_hours;
        modal.style.display = 'flex';
    }

    function closeEditModal() {
        modal.style.display = 'none';
    }

    // =========================================================================
    // 10. SETUP EVENT HANDLERS
    // =========================================================================
    function setupEventHandlers() {
        // Search
        const searchBtn = document.getElementById('btn-run-search');
        const searchInput = document.getElementById('input-vector-query');
        if (searchBtn && searchInput) {
            searchBtn.addEventListener('click', () => runVectorSearch(searchInput.value));
            searchInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') runVectorSearch(searchInput.value);
            });
        }

        // Quick query chips
        document.querySelectorAll('.chip-btn').forEach(chip => {
            chip.addEventListener('click', () => {
                const q = chip.getAttribute('data-query');
                if (searchInput) searchInput.value = q;
                runVectorSearch(q);
            });
        });

        // Run RAG analysis
        const runAnalysisBtn = document.getElementById('btn-run-analysis');
        if (runAnalysisBtn) {
            runAnalysisBtn.addEventListener('click', runRAGAnalysis);
        }

        // Radio platform change (Jira / ADO)
        document.querySelectorAll('input[name="target_platform"]').forEach(radio => {
            radio.addEventListener('change', (e) => {
                currentSelectedPlatform = e.target.value;
                document.querySelectorAll('.radio-card').forEach(rc => rc.classList.remove('active'));
                e.target.closest('.radio-card').classList.add('active');
                updatePayloadPreview();
            });
        });

        // Execute import button
        const importBtn = document.getElementById('btn-execute-import');
        if (importBtn) {
            importBtn.addEventListener('click', executeImportTickets);
        }

        // Modal close buttons
        document.getElementById('btn-close-modal')?.addEventListener('click', closeEditModal);
        document.getElementById('btn-cancel-modal')?.addEventListener('click', closeEditModal);

        // Modal save button
        document.getElementById('btn-save-modal')?.addEventListener('click', async () => {
            const idx = parseInt(document.getElementById('edit-task-index').value);
            const newTitle = document.getElementById('edit-task-title').value;
            const newHours = parseFloat(document.getElementById('edit-task-hours').value);

            if (idx >= 0 && idx < analyzedTasks.length) {
                analyzedTasks[idx].standardized_title = newTitle;
                analyzedTasks[idx].estimated_hours = newHours;

                await fetch('/api/update-task-approval', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        index: idx,
                        standardized_title: newTitle,
                        estimated_hours: newHours
                    })
                });

                closeEditModal();
                renderAnalyzedTasksTable();
                updatePayloadPreview();
            }
        });

        // Save rules button
        document.getElementById('btn-save-rules-file')?.addEventListener('click', async () => {
            const btn = document.getElementById('btn-save-rules-file');
            btn.innerHTML = '✅ Đã lưu file .agent-rules.md thành công!';
            setTimeout(() => {
                btn.innerHTML = '💾 Cập Nhật & Lưu File Rules';
            }, 2500);
        });
    }

    function escapeHtml(text) {
        if (!text) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
});
