/**
 * Embedded HTML5 Canvas Candlestick & Technical Indicator Engine
 * 100% Self-Contained, Zero CDN, Zero NPM Dependencies
 */
(function(window) {
    'use strict';

    function CanvasChartEngine(canvasElement, options) {
        this.canvas = canvasElement;
        this.ctx = canvasElement.getContext('2d');
        this.options = Object.assign({
            bullColor: '#00c076',
            bearColor: '#ff4d4f',
            bgGridColor: '#161f2b',
            textScaleColor: '#64748b',
            ema20Color: '#3b82f6',
            ema50Color: '#f5a623',
            rsiColor: '#a855f7',
            candleWidthRatio: 0.7,
            paddingRight: 60,
            paddingBottom: 24,
            volumeHeightPct: 0.18,
        }, options || {});

        this.candles = [];
        this.markers = [];
        this.proposal = null;
        this.mousePos = null;
        this.isHovering = false;

        this.init();
    }

    CanvasChartEngine.prototype.init = function() {
        var self = this;
        this.resize();

        window.addEventListener('resize', function() {
            self.resize();
        });

        this.canvas.addEventListener('mousemove', function(e) {
            var rect = self.canvas.getBoundingClientRect();
            self.mousePos = {
                x: e.clientX - rect.left,
                y: e.clientY - rect.top
            };
            self.isHovering = true;
            self.render();
        });

        this.canvas.addEventListener('mouseleave', function() {
            self.isHovering = false;
            self.mousePos = null;
            self.render();
        });
    };

    CanvasChartEngine.prototype.resize = function() {
        var rect = this.canvas.parentElement.getBoundingClientRect();
        var dpr = window.devicePixelRatio || 1;
        this.width = rect.width || 600;
        this.height = rect.height || 420;

        this.canvas.width = this.width * dpr;
        this.canvas.height = this.height * dpr;
        this.canvas.style.width = this.width + 'px';
        this.canvas.style.height = this.height + 'px';

        this.ctx.scale(dpr, dpr);
        this.render();
    };

    CanvasChartEngine.prototype.setCandles = function(candles) {
        this.candles = candles ? candles.slice() : [];
        this.computeIndicators();
        this.render();
    };

    CanvasChartEngine.prototype.updateLastCandle = function(candle) {
        if (!this.candles.length) {
            this.candles.push(candle);
        } else {
            var last = this.candles[this.candles.length - 1];
            if (last.timestamp_ms === candle.timestamp_ms) {
                this.candles[this.candles.length - 1] = candle;
            } else {
                this.candles.push(candle);
            }
        }
        this.computeIndicators();
        this.render();
    };

    CanvasChartEngine.prototype.addExecutionMarker = function(marker) {
        this.markers.push(marker);
        this.render();
    };

    CanvasChartEngine.prototype.setProposal = function(proposal) {
        this.proposal = proposal;
        this.render();
    };

    CanvasChartEngine.prototype.computeIndicators = function() {
        if (!this.candles.length) return;

        // Compute EMA 20
        var k20 = 2 / (20 + 1);
        var ema20 = this.candles[0].close;
        for (var i = 0; i < this.candles.length; i++) {
            ema20 = (this.candles[i].close * k20) + (ema20 * (1 - k20));
            this.candles[i].ema_20 = ema20;
        }

        // Compute EMA 50
        var k50 = 2 / (50 + 1);
        var ema50 = this.candles[0].close;
        for (var j = 0; j < this.candles.length; j++) {
            ema50 = (this.candles[j].close * k50) + (ema50 * (1 - k50));
            this.candles[j].ema_50 = ema50;
        }

        // Compute RSI 14
        var period = 14;
        if (this.candles.length > period) {
            var gains = 0, losses = 0;
            for (var r = 1; r <= period; r++) {
                var diff = this.candles[r].close - this.candles[r - 1].close;
                if (diff >= 0) gains += diff; else losses -= diff;
            }
            var avgGain = gains / period;
            var avgLoss = losses / period;
            for (var m = period + 1; m < this.candles.length; m++) {
                var d = this.candles[m].close - this.candles[m - 1].close;
                var g = d >= 0 ? d : 0;
                var l = d < 0 ? -d : 0;
                avgGain = (avgGain * 13 + g) / 14;
                avgLoss = (avgLoss * 13 + l) / 14;
                var rs = avgLoss === 0 ? 100 : (avgGain / avgLoss);
                this.candles[m].rsi_14 = 100 - (100 / (1 + rs));
            }
        }
    };

    CanvasChartEngine.prototype.render = function() {
        var ctx = this.ctx;
        var w = this.width;
        var h = this.height;

        ctx.clearRect(0, 0, w, h);

        if (!this.candles.length) {
            ctx.fillStyle = this.options.textScaleColor;
            ctx.font = '12px ui-monospace, monospace';
            ctx.fillText('Awaiting market telemetry ticks...', 20, 40);
            return;
        }

        var plotW = w - this.options.paddingRight;
        var plotH = h - this.options.paddingBottom;
        var volH = plotH * this.options.volumeHeightPct;
        var priceH = plotH - volH;

        // Min/Max Price calculation
        var minPrice = Infinity;
        var maxPrice = -Infinity;
        var maxVol = 0;

        for (var i = 0; i < this.candles.length; i++) {
            var c = this.candles[i];
            if (c.low < minPrice) minPrice = c.low;
            if (c.high > maxPrice) maxPrice = c.high;
            if (c.volume > maxVol) maxVol = c.volume;
        }

        // Add 5% padding
        var pricePad = (maxPrice - minPrice) * 0.05 || 10;
        minPrice -= pricePad;
        maxPrice += pricePad;
        var priceRange = maxPrice - minPrice;

        var candleCount = this.candles.length;
        var slotWidth = plotW / Math.max(candleCount, 20);
        var candleW = slotWidth * this.options.candleWidthRatio;

        // Draw horizontal price grid & labels
        ctx.strokeStyle = this.options.bgGridColor;
        ctx.lineWidth = 1;
        ctx.fillStyle = this.options.textScaleColor;
        ctx.font = '10px ui-monospace, monospace';
        ctx.textAlign = 'left';

        var steps = 5;
        for (var s = 0; s <= steps; s++) {
            var pVal = minPrice + (priceRange * (s / steps));
            var yPos = priceH - ((pVal - minPrice) / priceRange) * priceH;

            ctx.beginPath();
            ctx.moveTo(0, yPos);
            ctx.lineTo(plotW, yPos);
            ctx.stroke();

            ctx.fillText(pVal.toFixed(2), plotW + 6, yPos + 3);
        }

        // Draw Volume separator line
        ctx.beginPath();
        ctx.moveTo(0, priceH);
        ctx.lineTo(plotW, priceH);
        ctx.stroke();

        // Draw Candlesticks & Volume Bars
        for (var idx = 0; idx < candleCount; idx++) {
            var candle = this.candles[idx];
            var xCenter = idx * slotWidth + (slotWidth / 2);
            var xLeft = xCenter - (candleW / 2);

            var isUp = candle.close >= candle.open;
            var color = isUp ? this.options.bullColor : this.options.bearColor;

            var yHigh = priceH - ((candle.high - minPrice) / priceRange) * priceH;
            var yLow = priceH - ((candle.low - minPrice) / priceRange) * priceH;
            var yOpen = priceH - ((candle.open - minPrice) / priceRange) * priceH;
            var yClose = priceH - ((candle.close - minPrice) / priceRange) * priceH;

            // Wick
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.2;
            ctx.beginPath();
            ctx.moveTo(xCenter, yHigh);
            ctx.lineTo(xCenter, yLow);
            ctx.stroke();

            // Candle Body
            var bodyTop = Math.min(yOpen, yClose);
            var bodyHeight = Math.max(Math.abs(yClose - yOpen), 1.5);
            ctx.fillStyle = color;
            ctx.fillRect(xLeft, bodyTop, candleW, bodyHeight);

            // Volume bar
            if (maxVol > 0) {
                var vHeight = (candle.volume / maxVol) * (volH - 8);
                var vTop = plotH - vHeight;
                ctx.fillStyle = isUp ? 'rgba(0, 192, 118, 0.3)' : 'rgba(255, 77, 79, 0.3)';
                ctx.fillRect(xLeft, vTop, candleW, vHeight);
            }
        }

        // Draw EMA 20 & EMA 50
        this.drawCurve(slotWidth, minPrice, priceRange, priceH, 'ema_20', this.options.ema20Color);
        this.drawCurve(slotWidth, minPrice, priceRange, priceH, 'ema_50', this.options.ema50Color);

        // Draw Proposal Target and Stop-Loss lines
        if (this.proposal) {
            if (this.proposal.entry_price) {
                var yEntry = priceH - ((this.proposal.entry_price - minPrice) / priceRange) * priceH;
                this.drawDashedLine(0, yEntry, plotW, yEntry, '#3b82f6', 'ENTRY: $' + this.proposal.entry_price.toFixed(2));
            }
            if (this.proposal.stop_loss) {
                var yStop = priceH - ((this.proposal.stop_loss - minPrice) / priceRange) * priceH;
                this.drawDashedLine(0, yStop, plotW, yStop, '#ff4d4f', 'STOP: $' + this.proposal.stop_loss.toFixed(2));
            }
        }

        // Draw Execution Markers
        for (var k = 0; k < this.markers.length; k++) {
            var m = this.markers[k];
            var mY = priceH - ((m.price - minPrice) / priceRange) * priceH;
            var mX = (this.candles.length - 1) * slotWidth + (slotWidth / 2);

            ctx.fillStyle = m.type === 'EXECUTION_BUY' ? '#00c076' : '#ff4d4f';
            ctx.beginPath();
            if (m.type === 'EXECUTION_BUY') {
                ctx.moveTo(mX, mY - 14);
                ctx.lineTo(mX - 6, mY - 4);
                ctx.lineTo(mX + 6, mY - 4);
            } else {
                ctx.moveTo(mX, mY + 14);
                ctx.lineTo(mX - 6, mY + 4);
                ctx.lineTo(mX + 6, mY + 4);
            }
            ctx.fill();
        }

        // Draw Crosshair
        if (this.isHovering && this.mousePos && this.mousePos.x <= plotW && this.mousePos.y <= plotH) {
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
            ctx.setLineDash([4, 4]);

            // Vertical crosshair
            ctx.beginPath();
            ctx.moveTo(this.mousePos.x, 0);
            ctx.lineTo(this.mousePos.x, plotH);
            ctx.stroke();

            // Horizontal crosshair
            ctx.beginPath();
            ctx.moveTo(0, this.mousePos.y);
            ctx.lineTo(plotW, this.mousePos.y);
            ctx.stroke();
            ctx.setLineDash([]);

            // Price badge at right axis
            if (this.mousePos.y <= priceH) {
                var hoverPrice = maxPrice - (this.mousePos.y / priceH) * priceRange;
                ctx.fillStyle = '#3b82f6';
                ctx.fillRect(plotW, this.mousePos.y - 9, this.options.paddingRight, 18);
                ctx.fillStyle = '#ffffff';
                ctx.font = '10px ui-monospace, monospace';
                ctx.fillText(hoverPrice.toFixed(2), plotW + 4, this.mousePos.y + 4);
            }
        }
    };

    CanvasChartEngine.prototype.drawCurve = function(slotWidth, minPrice, priceRange, priceH, prop, color) {
        var ctx = this.ctx;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        var started = false;

        for (var i = 0; i < this.candles.length; i++) {
            var val = this.candles[i][prop];
            if (val === undefined || val === null) continue;

            var x = i * slotWidth + (slotWidth / 2);
            var y = priceH - ((val - minPrice) / priceRange) * priceH;

            if (!started) {
                ctx.moveTo(x, y);
                started = true;
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.stroke();
    };

    CanvasChartEngine.prototype.drawDashedLine = function(x1, y1, x2, y2, color, label) {
        var ctx = this.ctx;
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.2;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();

        ctx.fillStyle = color;
        ctx.font = '10px ui-monospace, monospace';
        ctx.fillText(label, x1 + 10, y1 - 4);
        ctx.restore();
    };

    window.CanvasChartEngine = CanvasChartEngine;
})(window);
