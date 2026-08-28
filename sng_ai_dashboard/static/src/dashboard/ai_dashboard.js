/** @odoo-module **/
/* global Chart */
import { Component, onWillStart, onWillUnmount, useState, useRef, useEffect, markup } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";

const MONTH_NAMES = {
    "01": "Ene", "02": "Feb", "03": "Mar", "04": "Abr", "05": "May", "06": "Jun",
    "07": "Jul", "08": "Ago", "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dic",
};

// Paleta: azul = facturado, aqua = cobrado; ramp cálido = severidad de morosidad.
const C = {
    sales: "#2a78d6",
    collected: "#1baf7a",
    aging: ["#2a78d6", "#c98500", "#eb6834", "#d03b3b", "#8f2323"],
    grid: "#e1e0d9",
    ink: "#898781",
    inkStrong: "#52514e",
};

function syncThemeColors() {
    const style = getComputedStyle(document.body);
    C.grid = style.getPropertyValue("--bs-border-color").trim() || "#e1e0d9";
    C.ink = style.getPropertyValue("--bs-secondary-color").trim() || "#898781";
    C.inkStrong = style.getPropertyValue("--bs-body-color").trim() || "#52514e";
}

const PERIODS = [1, 3, 6, 12];

// Etiquetas de valor al final de cada barra (relief para colores < 3:1)
const barValueLabels = {
    id: "sngBarValueLabels",
    afterDatasetsDraw(chart, _args, opts) {
        if (!opts || !opts.formatter) {
            return;
        }
        const { ctx } = chart;
        ctx.save();
        ctx.font = "11px system-ui, -apple-system, 'Segoe UI', sans-serif";
        ctx.fillStyle = C.inkStrong;
        const horizontal = chart.options.indexAxis === "y";
        for (const meta of chart.getSortedVisibleDatasetMetas()) {
            meta.data.forEach((bar, i) => {
                const value = meta.controller.getParsed(i)[horizontal ? "x" : "y"];
                const text = opts.formatter(value);
                if (horizontal) {
                    ctx.textAlign = "left";
                    ctx.textBaseline = "middle";
                    ctx.fillText(text, bar.x + 6, bar.y);
                } else {
                    ctx.textAlign = "center";
                    ctx.textBaseline = "bottom";
                    ctx.fillText(text, bar.x, bar.y - 4);
                }
            });
        }
        ctx.restore();
    },
};

export class AiDashboard extends Component {
    static template = "sng_ai_dashboard.AiDashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.periods = PERIODS;
        this.state = useState({
            loading: true,
            months: 3,
            tab: "general",
            data: null,
        });
        this.salesChartRef = useRef("salesChart");
        this.agingChartRef = useRef("agingChart");
        this.salespersonChartRef = useRef("salespersonChart");
        this.whValueChartRef = useRef("whValueChart");
        this.whCoverChartRef = useRef("whCoverChart");
        this.cxcMonthlyChartRef = useRef("cxcMonthlyChart");
        this.cxcAgingChartRef = useRef("cxcAgingChart");
        this.charts = [];

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            this.state.data = await this.orm.call(
                "sng.ai.dashboard", "get_dashboard_data", [], { months: this.state.months });
            this.state.loading = false;
        });
        // Se ejecuta tras cada patch del DOM: dibuja cuando los canvas existen
        useEffect(
            () => {
                if (!this.state.loading) {
                    this.renderCharts();
                }
            },
            () => [this.state.loading, this.state.tab]
        );
        onWillUnmount(() => this.destroyCharts());
    }

    // ------------------------------------------------------------------
    // Formato
    // ------------------------------------------------------------------

    get currencySymbol() {
        return (this.state.data && this.state.data.currency.symbol) || "₡";
    }

    fmtFull(value) {
        return this.currencySymbol + new Intl.NumberFormat("es-CR", {
            maximumFractionDigits: 0,
        }).format(value || 0);
    }

    fmtCompact(value) {
        const abs = Math.abs(value || 0);
        let text;
        if (abs >= 1e9) {
            text = (value / 1e9).toFixed(1) + "MM";
        } else if (abs >= 1e6) {
            text = (value / 1e6).toFixed(1) + "M";
        } else if (abs >= 1e3) {
            text = (value / 1e3).toFixed(0) + "K";
        } else {
            text = String(Math.round(value || 0));
        }
        return this.currencySymbol + text;
    }

    fmtPct(current, base) {
        if (!base) {
            return null;
        }
        const pct = ((current - base) / Math.abs(base)) * 100;
        return (pct >= 0 ? "+" : "") + pct.toFixed(1) + "%";
    }

    deltaClass(current, base) {
        if (!base) {
            return "text-muted";
        }
        return current >= base ? "o_sng_delta_up" : "o_sng_delta_down";
    }

    monthLabel(ym) {
        const [year, month] = ym.split("-");
        return `${MONTH_NAMES[month] || month} ${year.slice(2)}`;
    }

    pctOf(part, total) {
        if (!total) {
            return "0%";
        }
        return Math.round((part / total) * 100) + "%";
    }

    fmtDate(iso) {
        if (!iso) {
            return "—";
        }
        const [year, month, day] = iso.split("-");
        return `${day}/${month}/${year}`;
    }

    urgency(client) {
        const days = client.weighted_days || 0;
        const noRecentPayment = !client.last_payment;
        if (days > 90 || (days > 60 && noRecentPayment)) {
            return { label: "Crítico — gestión formal", cls: "o_sng_badge_critical" };
        }
        if (days > 60) {
            return { label: "Alto — llamar hoy", cls: "o_sng_badge_high" };
        }
        if (days > 30) {
            return { label: "Medio — llamar", cls: "o_sng_badge_medium" };
        }
        return { label: "Recordatorio", cls: "o_sng_badge_low" };
    }

    get currentAi() {
        const ai = this.state.data && this.state.data.ai;
        if (!ai || !ai.by_scope) {
            return false;
        }
        const scope = this.state.tab === "inventario" ? "inventory" : this.state.tab;
        return ai.by_scope[scope] || false;
    }

    get aiContent() {
        return this.currentAi ? markup(this.currentAi.content) : "";
    }

    get aiTitle() {
        return {
            general: "Análisis de ventas",
            customers: "Análisis de clientes",
            cxc: "Análisis de cuentas por cobrar",
            inventario: "Análisis de inventario",
        }[this.state.tab];
    }

    // ------------------------------------------------------------------
    // Gráficos
    // ------------------------------------------------------------------

    destroyCharts() {
        this.charts.forEach((c) => c.destroy());
        this.charts = [];
    }

    baseScales(horizontal) {
        const valueAxis = {
            grid: { color: C.grid, drawBorder: false },
            ticks: { color: C.ink, callback: (v) => this.fmtCompact(v) },
            beginAtZero: true,
        };
        const catAxis = {
            grid: { display: false },
            ticks: { color: C.inkStrong },
        };
        return horizontal ? { x: valueAxis, y: catAxis } : { x: catAxis, y: valueAxis };
    }

    tooltipOpts() {
        return {
            callbacks: {
                label: (ctx) => this.fmtFull(horizontalValue(ctx)),
            },
        };
        function horizontalValue(ctx) {
            return ctx.chart.options.indexAxis === "y" ? ctx.parsed.x : ctx.parsed.y;
        }
    }

    renderCharts() {
        if (!this.state.data) {
            return;
        }
        syncThemeColors();
        this.destroyCharts();
        const data = this.state.data;

        // Facturado vs cobrado por mes
        if (this.salesChartRef.el) {
            const monthly = data.sales.monthly;
            const collected = data.collections.monthly;
            this.charts.push(new Chart(this.salesChartRef.el, {
                type: "bar",
                data: {
                    labels: monthly.map((m) => this.monthLabel(m.month)),
                    datasets: [
                        {
                            label: "Facturado",
                            data: monthly.map((m) => m.total),
                            backgroundColor: C.sales,
                            borderRadius: 4,
                            maxBarThickness: 36,
                        },
                        {
                            label: "Cobrado",
                            data: collected.map((m) => m.total),
                            backgroundColor: C.collected,
                            borderRadius: 4,
                            maxBarThickness: 36,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: true,
                            position: "bottom",
                            labels: { color: C.inkStrong, boxWidth: 12, boxHeight: 12 },
                        },
                        tooltip: this.tooltipOpts(),
                    },
                    scales: this.baseScales(false),
                },
            }));
        }

        // Antigüedad CxC (barras horizontales, severidad por color) — se usa
        // en la pestaña General y en la de Cuentas por cobrar
        const makeAgingChart = (el) => {
            const b = data.receivables.buckets;
            this.charts.push(new Chart(el, {
                type: "bar",
                data: {
                    labels: ["Por vencer", "1-30 días", "31-60 días", "61-90 días", "+90 días"],
                    datasets: [{
                        data: [b.not_due, b.d1_30, b.d31_60, b.d61_90, b.d90_plus],
                        backgroundColor: C.aging,
                        borderRadius: 4,
                        maxBarThickness: 26,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: { padding: { right: 70 } },
                    plugins: {
                        legend: { display: false },
                        tooltip: this.tooltipOpts(),
                        sngBarValueLabels: { formatter: (v) => this.fmtCompact(v) },
                    },
                    scales: this.baseScales(true),
                },
                plugins: [barValueLabels],
            }));
        };
        if (this.agingChartRef.el) {
            makeAgingChart(this.agingChartRef.el);
        }
        if (this.cxcAgingChartRef.el) {
            makeAgingChart(this.cxcAgingChartRef.el);
        }

        // CxC: facturado (con IVA) vs cobrado por mes, con tasa de recuperación
        if (this.cxcMonthlyChartRef.el) {
            const rows = data.cxc.monthly;
            this.charts.push(new Chart(this.cxcMonthlyChartRef.el, {
                type: "bar",
                data: {
                    labels: rows.map((m) => this.monthLabel(m.month)),
                    datasets: [
                        {
                            label: "Facturado (con IVA)",
                            data: rows.map((m) => m.invoiced),
                            backgroundColor: C.sales,
                            borderRadius: 4,
                            maxBarThickness: 36,
                        },
                        {
                            label: "Cobrado",
                            data: rows.map((m) => m.collected),
                            backgroundColor: C.collected,
                            borderRadius: 4,
                            maxBarThickness: 36,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: true,
                            position: "bottom",
                            labels: { color: C.inkStrong, boxWidth: 12, boxHeight: 12 },
                        },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => `${ctx.dataset.label}: ${this.fmtFull(ctx.parsed.y)}`,
                                footer: (items) => {
                                    const rate = rows[items[0].dataIndex].rate;
                                    return rate !== null ? `Recuperación: ${rate}%` : "";
                                },
                            },
                        },
                    },
                    scales: this.baseScales(false),
                },
            }));
        }

        // Inventario WH: valor por categoría
        const wh = data.inventory_wh;
        if (wh && wh.available && this.whValueChartRef.el) {
            const cats = wh.by_category.slice(0, 10);
            this.charts.push(new Chart(this.whValueChartRef.el, {
                type: "bar",
                data: {
                    labels: cats.map((c) => c.category),
                    datasets: [{
                        data: cats.map((c) => c.value),
                        backgroundColor: C.sales,
                        borderRadius: 4,
                        maxBarThickness: 22,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: { padding: { right: 70 } },
                    plugins: {
                        legend: { display: false },
                        tooltip: this.tooltipOpts(),
                        sngBarValueLabels: { formatter: (v) => this.fmtCompact(v) },
                    },
                    scales: this.baseScales(true),
                },
                plugins: [barValueLabels],
            }));
        }

        // Inventario WH: meses de cobertura por categoría (severidad por color)
        if (wh && wh.available && this.whCoverChartRef.el) {
            const cats = wh.by_category.filter((c) => c.months_cover !== null).slice(0, 10);
            const coverColor = (m) => (m > 12 ? "#d03b3b" : m > 6 ? "#c98500" : C.sales);
            this.charts.push(new Chart(this.whCoverChartRef.el, {
                type: "bar",
                data: {
                    labels: cats.map((c) => c.category),
                    datasets: [{
                        data: cats.map((c) => c.months_cover),
                        backgroundColor: cats.map((c) => coverColor(c.months_cover)),
                        borderRadius: 4,
                        maxBarThickness: 22,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: { padding: { right: 70 } },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => {
                                    const cat = cats[ctx.dataIndex];
                                    return `${ctx.parsed.x} meses (venta prom. ${cat.monthly_avg} u/mes)`;
                                },
                            },
                        },
                        sngBarValueLabels: { formatter: (v) => v + " m" },
                    },
                    scales: {
                        x: {
                            grid: { color: C.grid, drawBorder: false },
                            ticks: { color: C.ink },
                            beginAtZero: true,
                        },
                        y: { grid: { display: false }, ticks: { color: C.inkStrong } },
                    },
                },
                plugins: [barValueLabels],
            }));
        }

        // Top vendedores del mes
        if (this.salespersonChartRef.el) {
            const rows = data.sales.by_salesperson;
            this.charts.push(new Chart(this.salespersonChartRef.el, {
                type: "bar",
                data: {
                    labels: rows.map((r) => r.name),
                    datasets: [{
                        data: rows.map((r) => r.total),
                        backgroundColor: C.sales,
                        borderRadius: 4,
                        maxBarThickness: 22,
                    }],
                },
                options: {
                    indexAxis: "y",
                    responsive: true,
                    maintainAspectRatio: false,
                    layout: { padding: { right: 70 } },
                    plugins: {
                        legend: { display: false },
                        tooltip: this.tooltipOpts(),
                        sngBarValueLabels: { formatter: (v) => this.fmtCompact(v) },
                    },
                    scales: this.baseScales(true),
                },
                plugins: [barValueLabels],
            }));
        }
    }

    // ------------------------------------------------------------------
    // Acciones
    // ------------------------------------------------------------------

    setTab(tab) {
        this.state.tab = tab;
    }

    async refresh() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "sng.ai.dashboard", "get_dashboard_data", [], { months: this.state.months });
        this.state.loading = false;
        // El useEffect sobre state.loading redibuja los gráficos tras el patch
    }

    async setPeriod(months) {
        if (months === this.state.months || this.state.loading) {
            return;
        }
        this.state.months = months;
        await this.refresh();
    }

}

registry.category("actions").add("sng_ai_dashboard", AiDashboard);
