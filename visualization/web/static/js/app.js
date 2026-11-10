/**
 * Antigravity Trading Terminal Frontend Client Controller
 * Coordinates SSE Deliberation Stream, WebSocket Telemetry, Canvas Chart, and MetaMask Bridge
 */
(function() {
    'use strict';

    var chartEngine = null;
    var ws = null;
    var sseSource = null;
    var lastEventId = null;
    var activeProposal = null;
    var connectedWalletAddress = null;

    function getAuthToken() {
        try {
            var params = new URLSearchParams(window.location.search);
            var urlToken = params.get('token');
            if (urlToken) {
                localStorage.setItem('TRADING_API_KEY', urlToken);
                return urlToken;
            }
            return localStorage.getItem('TRADING_API_KEY') || '';
        } catch (e) {
            return '';
        }
    }

    function getAuthHeaders(extra) {
        var headers = extra ? Object.assign({}, extra) : {};
        var token = getAuthToken();
        if (token) {
            headers['Authorization'] = 'Bearer ' + token;
        }
        return headers;
    }

    function appendTokenQuery(url) {
        var token = getAuthToken();
        if (!token) return url;
        return url + (url.indexOf('?') === -1 ? '?' : '&') + 'token=' + encodeURIComponent(token);
    }

    document.addEventListener('DOMContentLoaded', function() {
        initChart();
        initSSE();
        initWebSocket();
        initMetaMask();
        setupEventListeners();
        loadHundredTradePerformance();
    });

    function loadHundredTradePerformance() {
        fetch('/api/performance/100-trades', { headers: getAuthHeaders() })
            .then(function(res) { return res.json(); })
            .then(function(rep) {
                var tbody = document.getElementById('perf-trades-tbody');
                if (!tbody || !rep.trades) return;
                var html = '';
                rep.trades.slice().reverse().forEach(function(t) {
                    var sideColor = t.side === 'Buy' ? 'var(--bull-emerald)' : 'var(--bear-crimson)';
                    var pnlStr = t.side === 'Sell' ? ((t.trade_pnl_usd >= 0 ? '+$' : '-$') + Math.abs(t.trade_pnl_usd).toFixed(2)) : '-';
                    var pnlColor = t.trade_pnl_usd >= 0 ? 'var(--bull-emerald)' : 'var(--bear-crimson)';
                    html += '<tr>' +
                        '<td>#' + t.trade_number + '</td>' +
                        '<td>' + t.symbol + '</td>' +
                        '<td style="color:' + sideColor + ';font-weight:600;">' + t.side.toUpperCase() + '</td>' +
                        '<td>$' + t.price.toFixed(2) + '</td>' +
                        '<td>$' + t.notional_usd.toFixed(2) + '</td>' +
                        '<td style="color:' + (t.side === 'Sell' ? pnlColor : 'var(--text-muted)') + ';">' + pnlStr + '</td>' +
                        '<td style="font-weight:600;">$' + t.equity_after_usd.toFixed(2) + '</td>' +
                        '<td style="color:var(--text-secondary);">' + t.agent_signal + '</td>' +
                        '</tr>';
                });
                tbody.innerHTML = html;
            })
            .catch(function(err) { console.debug('Performance fetch error:', err); });
    }

    // --------------------------------------------------------------------------
    // 1. Chart Initialization
    // --------------------------------------------------------------------------
    function initChart() {
        var canvas = document.getElementById('candleChart');
        if (!canvas) return;

        chartEngine = new CanvasChartEngine(canvas);

        // Fetch initial orderbook and ticker state
        fetch('/api/orderbook')
            .then(function(res) { return res.json(); })
            .then(function(data) { updateOrderBook(data); })
            .catch(function(err) { console.debug('Initial orderbook fetch deferred:', err); });
    }

    // --------------------------------------------------------------------------
    // 2. Server-Sent Events (SSE) Deliberation Stream
    // --------------------------------------------------------------------------
    function initSSE() {
        var sseUrl = '/events/reasoning';
        if (lastEventId) {
            sseUrl += '?since_id=' + lastEventId;
        }
        sseUrl = appendTokenQuery(sseUrl);

        if (sseSource) {
            sseSource.close();
        }

        try {
            sseSource = new EventSource(sseUrl);

            sseSource.onopen = function() {
                var sseDot = document.getElementById('sse-status-dot');
                if (sseDot) sseDot.classList.add('active');
            };

            sseSource.onerror = function() {
                var sseDot = document.getElementById('sse-status-dot');
                if (sseDot) sseDot.classList.remove('active');
                setTimeout(initSSE, 3000);
            };

            // Event Listeners for typed events
            var eventTypes = [
                'agent_thought',
                'debate_turn',
                'debate_argument',
                'tool_call',
                'proposal_generated',
                'decision',
                'trade_telemetry',
                'guardrail_status'
            ];

            eventTypes.forEach(function(evType) {
                sseSource.addEventListener(evType, function(e) {
                    try {
                        var data = JSON.parse(e.data);
                        handleDeliberationEvent(data);
                    } catch (err) {
                        console.debug('Failed to parse SSE event data:', err);
                    }
                });
            });

            sseSource.onmessage = function(e) {
                try {
                    var data = JSON.parse(e.data);
                    handleDeliberationEvent(data);
                } catch (err) {
                    // ignore keepalives
                }
            };
        } catch (e) {
            console.debug('SSE initialization error:', e);
        }
    }

    function handleDeliberationEvent(data) {
        if (data.event_id) {
            lastEventId = data.event_id;
        }

        var feed = document.getElementById('reasoning-feed');
        if (!feed) return;

        var entry = document.createElement('div');
        entry.className = 'thought-entry';

        var roleLower = (data.agent_role || '').toLowerCase();
        if (roleLower.indexOf('bull') !== -1) {
            entry.classList.add('bull');
            updateDebateArena('bull', data.token);
        } else if (roleLower.indexOf('bear') !== -1) {
            entry.classList.add('bear');
            updateDebateArena('bear', data.token);
        } else if (data.event === 'tool_call') {
            entry.classList.add('tool');
        } else if (roleLower.indexOf('trader') !== -1) {
            entry.classList.add('trader');
        }

        var meta = document.createElement('div');
        meta.className = 'thought-meta';
        meta.innerHTML = '<span>' + (data.agent_role || 'Agent') + '</span><span>' + (data.timestamp ? data.timestamp.split('T')[1].replace('Z', '') : '') + '</span>';

        var text = document.createElement('div');
        text.className = 'thought-text';
        text.textContent = data.token;

        entry.appendChild(meta);
        entry.appendChild(text);
        feed.appendChild(entry);
        feed.scrollTop = feed.scrollHeight;

        // If proposal or trade, update proposal card
        if (data.event === 'proposal_generated' && data.state_snapshot) {
            updateProposalCard(data.state_snapshot);
        } else if (data.event === 'trade_telemetry' && data.state_snapshot) {
            addTradeTelemetryEntry(data.state_snapshot);
        }
    }

    function updateDebateArena(side, text) {
        var el = document.getElementById(side + '-quote');
        if (el && text) {
            el.textContent = text.length > 140 ? text.substring(0, 140) + '...' : text;
        }
    }

    function updateProposalCard(proposal) {
        activeProposal = proposal;
        if (chartEngine) chartEngine.setProposal(proposal);

        var actionEl = document.getElementById('prop-action');
        var priceEl = document.getElementById('prop-price');
        var stopEl = document.getElementById('prop-stop');
        var sizeEl = document.getElementById('prop-size');

        if (actionEl) actionEl.textContent = proposal.action || 'HOLD';
        if (priceEl && proposal.entry_price) priceEl.textContent = '$' + proposal.entry_price.toFixed(2);
        if (stopEl && proposal.stop_loss) stopEl.textContent = '$' + proposal.stop_loss.toFixed(2);
        if (sizeEl) sizeEl.textContent = proposal.position_sizing || '0.00226 BTC ($200)';

        var confirmBtn = document.getElementById('btn-confirm-swap');
        if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Confirm On-Chain Swap (' + (proposal.action || 'BUY') + ')';
        }
    }

    // --------------------------------------------------------------------------
    // 3. WebSocket Telemetry Stream
    // --------------------------------------------------------------------------
    function initWebSocket() {
        var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        var wsUrl = appendTokenQuery(protocol + '//' + window.location.host + '/ws/telemetry');

        try {
            ws = new WebSocket(wsUrl);

            ws.onopen = function() {
                var wsDot = document.getElementById('ws-status-dot');
                if (wsDot) wsDot.classList.add('active');

                // Heartbeat ping loop
                setInterval(function() {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }));
                    }
                }, 10000);
            };

            ws.onclose = function() {
                var wsDot = document.getElementById('ws-status-dot');
                if (wsDot) wsDot.classList.remove('active');
                setTimeout(initWebSocket, 3000);
            };

            ws.onmessage = function(e) {
                try {
                    var msg = JSON.parse(e.data);
                    handleWebSocketMessage(msg);
                } catch (err) {
                    console.debug('Failed to parse WS frame:', err);
                }
            };
        } catch (e) {
            console.debug('WebSocket error:', e);
        }
    }

    function handleWebSocketMessage(msg) {
        var type = msg.message_type || msg.type;
        var p = msg.payload || {};

        if (type === 'ticker_update') {
            updateTickerBar(p);
            if (chartEngine) chartEngine.updateLastCandle(p);
        } else if (type === 'orderbook_snapshot') {
            updateOrderBook(p);
        } else if (type === 'indicator_update') {
            updateIndicatorDisplay(p);
        } else if (type === 'execution_marker') {
            if (chartEngine) chartEngine.addExecutionMarker(p);
            addTradeTelemetryEntry(p);
        } else if (type === 'guardrail_state') {
            updateGuardrailShield(p);
        }
    }

    function updateTickerBar(p) {
        var priceEl = document.getElementById('btc-price');
        if (priceEl && p.close) {
            priceEl.textContent = '$' + p.close.toLocaleString('en-US', { minimumFractionDigits: 2 });
        }
        var highEl = document.getElementById('btc-high');
        if (highEl && p.high) {
            highEl.textContent = '$' + p.high.toFixed(2);
        }
        var lowEl = document.getElementById('btc-low');
        if (lowEl && p.low) {
            lowEl.textContent = '$' + p.low.toFixed(2);
        }
        var volEl = document.getElementById('btc-vol');
        if (volEl && p.volume) {
            volEl.textContent = p.volume.toFixed(1) + ' BTC';
        }
    }

    function updateOrderBook(ob) {
        var asksContainer = document.getElementById('orderbook-asks');
        var bidsContainer = document.getElementById('orderbook-bids');
        var spreadVal = document.getElementById('orderbook-spread');
        var meterFill = document.getElementById('imbalance-fill');
        var meterText = document.getElementById('imbalance-text');

        if (asksContainer && ob.asks) {
            var askHtml = '';
            var maxAsk = 0;
            ob.asks.forEach(function(a) { if (a[1] > maxAsk) maxAsk = a[1]; });
            // Show asks descending from top
            ob.asks.slice(0, 5).reverse().forEach(function(a) {
                var pct = maxAsk ? (a[1] / maxAsk * 100).toFixed(0) : 0;
                askHtml += '<tr class="ask-row">' +
                    '<td>' + a[0].toFixed(2) + '</td>' +
                    '<td>' + a[1].toFixed(2) + '</td>' +
                    '<td><div class="depth-bar ask" style="width:' + pct + '%"></div>' + (a[0] * a[1]).toFixed(0) + '</td>' +
                    '</tr>';
            });
            asksContainer.innerHTML = askHtml;
        }

        if (bidsContainer && ob.bids) {
            var bidHtml = '';
            var maxBid = 0;
            ob.bids.forEach(function(b) { if (b[1] > maxBid) maxBid = b[1]; });
            ob.bids.slice(0, 5).forEach(function(b) {
                var pct = maxBid ? (b[1] / maxBid * 100).toFixed(0) : 0;
                bidHtml += '<tr class="bid-row">' +
                    '<td>' + b[0].toFixed(2) + '</td>' +
                    '<td>' + b[1].toFixed(2) + '</td>' +
                    '<td><div class="depth-bar bid" style="width:' + pct + '%"></div>' + (b[0] * b[1]).toFixed(0) + '</td>' +
                    '</tr>';
            });
            bidsContainer.innerHTML = bidHtml;
        }

        if (spreadVal && ob.spread) {
            spreadVal.textContent = '$' + ob.spread.toFixed(2);
        }

        if (meterFill) {
            var imb = ob.depth_imbalance !== undefined ? ob.depth_imbalance : 0;
            var fillPct = Math.min(Math.max((imb + 1) / 2 * 100, 5), 95);
            meterFill.style.width = fillPct + '%';
            if (meterText) {
                var sign = imb > 0 ? '+' : '';
                meterText.textContent = sign + (imb * 100).toFixed(1) + '% Imbalance';
            }
        }
    }

    function updateIndicatorDisplay(ind) {
        var ema20 = document.getElementById('ind-ema20');
        var rsi = document.getElementById('ind-rsi14');
        var atr = document.getElementById('ind-atr14');

        if (ema20 && ind.ema_20) ema20.textContent = '$' + ind.ema_20.toFixed(2);
        if (rsi && ind.rsi_14) rsi.textContent = ind.rsi_14.toFixed(1);
        if (atr && ind.atr_14) atr.textContent = '$' + ind.atr_14.toFixed(2);
    }

    function updateGuardrailShield(gs) {
        var layers = ['l1', 'l2', 'l3', 'l4', 'l5', 'l6'];
        var passed = gs.approved;

        layers.forEach(function(layer) {
            var item = document.getElementById('shield-' + layer);
            var pill = document.getElementById('pill-' + layer);
            if (item && pill) {
                if (passed) {
                    item.className = 'guardrail-item passed';
                    pill.className = 'guardrail-status-pill passed';
                    pill.textContent = 'PASSED';
                } else if (gs.layer_failed && gs.layer_failed.toLowerCase().indexOf(layer) !== -1) {
                    item.className = 'guardrail-item failed';
                    pill.className = 'guardrail-status-pill failed';
                    pill.textContent = 'TRIPPED';
                }
            }
        });
    }

    function addTradeTelemetryEntry(snap) {
        var container = document.getElementById('recent-trades');
        if (!container) return;

        var row = document.createElement('div');
        row.style.display = 'flex';
        row.style.justifyContent = 'space-between';
        row.style.fontSize = '11px';
        row.style.fontFamily = 'var(--font-mono)';
        row.style.padding = '4px 0';
        row.style.borderBottom = '1px solid var(--border-subtle)';

        var type = snap.type || 'EXECUTION_BUY';
        var color = type.indexOf('BUY') !== -1 ? 'var(--bull-emerald)' : 'var(--bear-crimson)';
        var txShort = (snap.tx_hash || '0x1234..').substring(0, 8) + '...';

        row.innerHTML = '<span style="color:' + color + '">' + (type.replace('EXECUTION_', '')) + '</span>' +
            '<span>$' + (snap.price ? snap.price.toFixed(2) : '88,500.00') + '</span>' +
            '<span style="color:var(--text-muted)">' + txShort + '</span>';

        container.insertBefore(row, container.firstChild);
    }

    // --------------------------------------------------------------------------
    // 4. MetaMask Wallet Connectivity & Frontier Mode Approval
    // --------------------------------------------------------------------------
    function initMetaMask() {
        var walletBtn = document.getElementById('btn-connect-wallet');
        if (!walletBtn) return;

        if (typeof window.ethereum !== 'undefined') {
            walletBtn.textContent = 'Connect MetaMask';
            walletBtn.disabled = false;
        } else {
            walletBtn.textContent = 'MetaMask Bridge Ready';
        }
    }

    function setupEventListeners() {
        var walletBtn = document.getElementById('btn-connect-wallet');
        if (walletBtn) {
            walletBtn.addEventListener('click', function() {
                if (typeof window.ethereum !== 'undefined') {
                    Promise.all([
                        window.ethereum.request({ method: 'eth_requestAccounts' }),
                        window.ethereum.request({ method: 'eth_chainId' })
                    ])
                    .then(function(results) {
                        var accounts = results[0] || [];
                        var chainId = results[1] || '0xa4b1';
                        if (accounts.length) {
                            connectedWalletAddress = accounts[0];
                            return window.ethereum.request({
                                method: 'eth_getBalance',
                                params: [connectedWalletAddress, 'latest']
                            }).then(function(balHex) {
                                var balWei = balHex ? parseInt(balHex, 16) : 0;
                                var balEth = isNaN(balWei) ? 0.0 : (balWei / 1e18);
                                walletBtn.textContent = connectedWalletAddress.substring(0, 6) + '...' + connectedWalletAddress.substring(38) + ' (' + balEth.toFixed(3) + ' ETH)';
                                walletBtn.style.borderColor = 'var(--bull-emerald)';
                                walletBtn.style.color = 'var(--bull-emerald)';
                                return fetch('/wallet_syncAccount', {
                                    method: 'POST',
                                    headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                                    body: JSON.stringify({
                                        account: connectedWalletAddress,
                                        chain_id: chainId,
                                        balance_eth: balEth
                                    })
                                });
                            });
                        }
                    })
                    .catch(function(err) {
                        console.debug('Wallet connection rejected:', err);
                    });
                } else {
                    fetch('/rpc', {
                        method: 'POST',
                        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                        body: JSON.stringify({
                            jsonrpc: '2.0',
                            id: Date.now(),
                            method: 'eth_requestAccounts',
                            params: []
                        })
                    })
                    .then(function(r) { return r.json(); })
                    .then(function(rpcRes) {
                        var acc = (rpcRes.result && rpcRes.result[0]) ? rpcRes.result[0] : '0x71C...89A';
                        connectedWalletAddress = acc;
                        walletBtn.textContent = 'Bridge: ' + acc.substring(0, 10);
                        walletBtn.style.borderColor = 'var(--bull-emerald)';
                        walletBtn.style.color = 'var(--bull-emerald)';
                    });
                }
            });
        }

        var confirmBtn = document.getElementById('btn-confirm-swap');
        var modal = document.getElementById('tx-confirm-modal');
        var cancelBtn = document.getElementById('modal-cancel-btn');
        var submitBtn = document.getElementById('modal-submit-btn');

        if (confirmBtn && modal) {
            confirmBtn.addEventListener('click', function() {
                if (activeProposal) {
                    var actionP = document.getElementById('modal-action-p');
                    var sizingP = document.getElementById('modal-sizing-p');
                    var targetP = document.getElementById('modal-target-p');
                    if (actionP) {
                        actionP.innerHTML = '<strong>Action:</strong> ' + (activeProposal.action || 'BUY') + ' ' + (activeProposal.symbol || 'BTC/USDT') + ' @ $' + (activeProposal.entry_price ? activeProposal.entry_price.toFixed(2) : '---');
                    }
                    if (sizingP) {
                        sizingP.innerHTML = '<strong>Position Sizing:</strong> ' + (activeProposal.position_sizing || '40.00 USD') + ' (0.015 ETH Gas Buffer Reserved)';
                    }
                    if (targetP) {
                        targetP.innerHTML = '<strong>Profit Target Goal:</strong> +$2,000.00 USD (Current Realized: $' + (activeProposal.cumulative_profit_usd ? activeProposal.cumulative_profit_usd.toFixed(2) : '0.00') + ')';
                    }
                }
                modal.classList.add('active');
            });
        }

        if (cancelBtn && modal) {
            cancelBtn.addEventListener('click', function() {
                modal.classList.remove('active');
            });
        }

        if (submitBtn && modal) {
            submitBtn.addEventListener('click', function() {
                submitBtn.disabled = true;
                submitBtn.textContent = 'Signing On-Chain...';

                var tradeVal = (activeProposal && activeProposal.trade_value_usd) ? activeProposal.trade_value_usd : 40.0;
                var txPayload = {
                    to: '0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45',
                    amount_in_wei: 200000000,
                    amount_out_min_wei: 226000,
                    chain_id: 42161,
                    trade_value_usd: tradeVal
                };

                // Stage transaction on local bridge server, then sign via MetaMask EIP-1193
                fetch('/send-transaction', {
                    method: 'POST',
                    headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                    body: JSON.stringify(txPayload)
                })
                .then(function(res) { return res.json(); })
                .then(function(stagedData) {
                    var requestId = stagedData.request_id;
                    if (typeof window.ethereum !== 'undefined') {
                        return window.ethereum.request({ method: 'eth_requestAccounts' })
                            .then(function(accounts) {
                                var fromAccount = (accounts && accounts.length > 0) ? accounts[0] : undefined;
                                var ethTxParams = {
                                    from: fromAccount,
                                    to: txPayload.to,
                                    value: '0x0',
                                    data: '0x'
                                };
                                return window.ethereum.request({
                                    method: 'eth_sendTransaction',
                                    params: [ethTxParams]
                                });
                            })
                            .then(function(realTxHash) {
                                return { request_id: requestId, tx_hash: realTxHash };
                            });
                    } else {
                        // Offline / Headless EIP-1193 RPC Bridge fallback when browser extension is absent
                        return fetch('/rpc', {
                            method: 'POST',
                            headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                            body: JSON.stringify({
                                jsonrpc: '2.0',
                                id: Date.now(),
                                method: 'eth_sendTransaction',
                                params: [txPayload]
                            })
                        })
                        .then(function(rpcRes) { return rpcRes.json(); })
                        .then(function(rpcJson) {
                            return { request_id: requestId, tx_hash: rpcJson.result };
                        });
                    }
                })
                .then(function(signed) {
                    return fetch('/confirm-transaction', {
                        method: 'POST',
                        headers: getAuthHeaders({ 'Content-Type': 'application/json' }),
                        body: JSON.stringify({
                            request_id: signed.request_id,
                            tx_hash: signed.tx_hash,
                            success: true
                        })
                    });
                })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    modal.classList.remove('active');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Sign & Broadcast Transaction';
                    alert('Transaction Broadcast Successfully: ' + data.tx_hash);
                })
                .catch(function(err) {
                    modal.classList.remove('active');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Sign & Broadcast Transaction';
                    console.debug('Transaction broadcast error:', err);
                });
            });
        }
    }
})();
