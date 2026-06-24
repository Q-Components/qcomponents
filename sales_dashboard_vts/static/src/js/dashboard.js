/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart ,onMounted} from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";
class SalesDashboard extends Component {

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.topProductsPageSize = 5;
        this.topProductsChartInstance = null;

        this.topCustomersPageSize = 5;
        this.topCustomersChartInstance = null;

        this.cityQuantityPageSize = 5;
        this.cityQuantityChartInstance = null;

        this.carrierShippingPageSize = 5;
        this.carrierShippingChartInstance = null;
        this.topSuppliersChartInstance = null;
        


        const formatDate = (date) => {
            const year = date.getFullYear();
            const month = String(date.getMonth() + 1).padStart(2, "0");
            const day = String(date.getDate()).padStart(2, "0");

            return `${year}-${month}-${day}`;
        };

        const today = new Date();

        const fromDate = new Date(
            today.getFullYear(),
            today.getMonth(),
            1
        );

        this.state = useState({
            dashboard_data: {
                kpis: {},
            },

            filters: {
                date_from: formatDate(fromDate),
                date_to: formatDate(today),
            },
            topProductsPage: 0,  
            topCustomersPage: 0, 
            cityQuantityPage: 0, 
            carrierShippingPage: 0,
        });

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.loadDashboardData();
        });
        onMounted(() => {
            this.renderMonthlySalesChart();
            this.renderInvoiceStatusChart();
            this.renderTopProductsChart();
            this.renderTopCustomersChart();
            this.renderCityQuantityChart();
            this.renderDeliveryStatusChart();
            this.renderCarrierShippingChart();
            this.renderTopSuppliersChart(); 
            this.renderTopPurchasedProductsChart();
            
        });
    }

    async loadDashboardData() {

        this.state.dashboard_data = await this.orm.call(
            "sale.order",
            "get_dashboard_data",
            [
                this.state.filters.date_from,
                this.state.filters.date_to,
            ]
        );
    }

    openRecords(model, name, domain = []) {

        const finalDomain = [...domain];
        if (this.state.filters.date_from) {
            finalDomain.push([
                "date_order",
                ">=",
                this.state.filters.date_from + " 00:00:00"
            ]);
        }

        if (this.state.filters.date_to) {
            finalDomain.push([
                "date_order",
                "<=",
                this.state.filters.date_to + " 23:59:59"
            ]);
        }

        this.action.doAction({
            type: "ir.actions.act_window",
            name: name,
            res_model: model,
            views: [
                [false, "list"],
                [false, "form"]
            ],
            target: "current",
            domain: finalDomain,
        });
    }


    openInvoiceRecords(ids, title) {

        this.action.doAction({
            type: "ir.actions.act_window",
            name: title,
            res_model: "account.move",
            views: [
                [false, "list"],
                [false, "form"]
            ],
            target: "current",
            domain: [["id", "in", ids]],
        });
    }

    openDeliveryRecords(ids, title) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: title,
            res_model: "stock.picking",
            views: [
                [false, "list"],
                [false, "form"]
            ],
            target: "current",
            domain: [["id", "in", ids]],
        });
    }
    openReturnRecords() {
        const ids = this.state.dashboard_data.records.return_ids || [];
        
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Returns",
            res_model: "stock.picking",
            views: [[false, "list"], [false, "form"]],
            target: "current",
            domain: [["id", "in", ids]],
        });
    }

    openShippingRecords() {
        const domain = [
            ['order_line.is_delivery', '=', true],
            ['state', 'in', ['sale', 'done']],
        ];

        if (this.state.filters.date_from) {
            domain.push(['date_order', '>=', this.state.filters.date_from + " 00:00:00"]);
        }
        if (this.state.filters.date_to) {
            domain.push(['date_order', '<=', this.state.filters.date_to + " 23:59:59"]);
        }

        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Orders with Shipping Charges",
            res_model: "sale.order",
            views: [[false, "list"], [false, "form"]],
            target: "current",
            domain: domain,
        });
    }
    // Pages
    get topProductsTotalPages() {
        const data = this.state.dashboard_data.charts?.top_products || [];
        return Math.max(Math.ceil(data.length / this.topProductsPageSize), 1);
    }

    nextTopProductsPage() {
        if (this.state.topProductsPage < this.topProductsTotalPages - 1) {
            this.state.topProductsPage++;
            this.renderTopProductsChart();
        }
    }

    prevTopProductsPage() {
        if (this.state.topProductsPage > 0) {
            this.state.topProductsPage--;
            this.renderTopProductsChart();
        }
    }

    get topCustomersTotalPages() {
        const data = this.state.dashboard_data.charts?.top_customers || [];
        return Math.max(Math.ceil(data.length / this.topCustomersPageSize), 1);
    }

    nextTopCustomersPage() {
        if (this.state.topCustomersPage < this.topCustomersTotalPages - 1) {
            this.state.topCustomersPage++;
            this.renderTopCustomersChart();
        }
    }

    prevTopCustomersPage() {
        if (this.state.topCustomersPage > 0) {
            this.state.topCustomersPage--;
            this.renderTopCustomersChart();
        }
    }

    get cityQuantityTotalPages() {
        const data = this.state.dashboard_data.charts?.city_quantity || [];
        return Math.max(Math.ceil(data.length / this.cityQuantityPageSize), 1);
    }

    nextCityQuantityPage() {
        if (this.state.cityQuantityPage < this.cityQuantityTotalPages - 1) {
            this.state.cityQuantityPage++;
            this.renderCityQuantityChart();
        }
    }

    prevCityQuantityPage() {
        if (this.state.cityQuantityPage > 0) {
            this.state.cityQuantityPage--;
            this.renderCityQuantityChart();
        }
    }

    get carrierShippingTotalPages() {
        const data = this.state.dashboard_data.charts?.carrier_shipping || [];
        return Math.max(Math.ceil(data.length / this.carrierShippingPageSize), 1);
    }

    nextCarrierShippingPage() {
        if (this.state.carrierShippingPage < this.carrierShippingTotalPages - 1) {
            this.state.carrierShippingPage++;
            this.renderCarrierShippingChart();
        }
    }

    prevCarrierShippingPage() {
        if (this.state.carrierShippingPage > 0) {
            this.state.carrierShippingPage--;
            this.renderCarrierShippingChart();
        }
    }

    // Graphs
    renderTopSuppliersChart() {

        const allData =
            this.state.dashboard_data?.charts?.top_suppliers || [];

        const canvas = document.getElementById("topSuppliersChart");

        console.log("TOP SUPPLIERS DATA =>", allData);  

        if (!canvas) {
            console.warn("Canvas not found: topSuppliersChart");
            return;
        }

        if (!allData.length) {
            console.warn("No supplier data found");
            return;
        }

        const labels = allData.map(item => item.supplier || "Unknown");
        const values = allData.map(item => item.amount || 0);

        // destroy old chart if exists
        if (this.topSuppliersChartInstance) {
            this.topSuppliersChartInstance.destroy();
        }

        this.topSuppliersChartInstance = new Chart(canvas, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: "Top Suppliers",
                    data: values,
                    backgroundColor: "#22C55E",
                    borderRadius: 6,
                    maxBarThickness: 20,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,

                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                return Number(context.raw || 0).toLocaleString();
                            }
                        }
                    }
                },

                scales: {
                    x: {
                        grid: { display: false },
                        ticks: {
                            autoSkip: false,
                            maxRotation: 30,
                            minRotation: 0
                        }
                    },
                    y: {
                        beginAtZero: true,
                        grid: { display: false }
                    }
                }
            }
        });
    }

    renderTopPurchasedProductsChart() {

        const allData =
            this.state.dashboard_data.charts?.top_purchased_products || [];

        const canvas =
            document.getElementById("topPurchasedProductsChart");

        if (!canvas || !allData.length) {
            return;
        }

        if (this.topPurchasedProductsChartInstance) {
            this.topPurchasedProductsChartInstance.destroy();
        }

        const labels = allData.map(item => item.product);
        // const amounts = allData.map(item => item.amount);
        const qty = allData.map(item => item.qty)

        const formatAmount = (value) => {
            if (value >= 1000000) {
                return (value / 1000000).toFixed(1) + "M";
            }
            if (value >= 1000) {
                return (value / 1000).toFixed(1) + "K";
            }
            return value.toLocaleString();
        };

        this.topPurchasedProductsChartInstance = new Chart(canvas, {
            type: "bar",

            data: {
                labels: labels,
                datasets: [{
                    data: qty,
                    backgroundColor: "#14B8A6",
                    borderRadius: 6,
                    barThickness: 14,
                }]
            },

            options: {
                indexAxis: "y",

                responsive: true,
                maintainAspectRatio: false,

                layout: {
                    padding: {
                        right: 60
                    }
                },

                plugins: {
                    legend: {
                        display: false
                    },

                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return formatAmount(context.raw);
                            }
                        }
                    }
                },

                scales: {
                    x: {
                        display: false,
                        grid: {
                            display: false
                        },
                        border: {
                            display: false
                        }
                    },

                    y: {
                        grid: {
                            display: false
                        },

                        border: {
                            display: false
                        },

                        ticks: {
                            font: {
                                size: 12
                            }
                        }
                    }
                }
            },

            plugins: [{
                id: "valueLabels",

                afterDatasetsDraw(chart) {

                    const { ctx } = chart;

                    ctx.save();

                    chart.getDatasetMeta(0).data.forEach(
                        (bar, index) => {

                            ctx.fillStyle = "#374151";
                            ctx.font = "12px Arial";

                            ctx.fillText(
                                formatAmount(qty[index]),
                                bar.x + 10,
                                bar.y + 4
                            );
                        }
                    );

                    ctx.restore();
                }
            }]
        });
    }

    renderMonthlySalesChart() {

        const chartData =
            this.state.dashboard_data.charts.monthly_sales;

        const labels = chartData.map(
            item => item.month
        );

        const sales = chartData.map(
            item => item.sales
        );

        const canvas =
            document.getElementById(
                "monthlySalesChart"
            );

        if (!canvas) {
            return;
        }

        new Chart(canvas, {
            type: "line",

            data: {
                labels: labels,

                datasets: [{
                    label: "Sales Amount",
                    data: sales,

                    borderColor: "#2563EB",               // Blue line
                    backgroundColor: "rgba(37,99,235,0.15)",

                    pointBackgroundColor: "#06B6D4",     // Cyan points
                    pointBorderColor: "#FFFFFF",
                    pointBorderWidth: 2,

                    tension: 0.4,
                    borderWidth: 3,
                    pointRadius: 5,
                    pointHoverRadius: 7,

                    fill: true,
                }]
            },

            options: {
                responsive: false,
                maintainAspectRatio: false,

                plugins: {
                    legend: {
                        display: false
                    }
                },

                scales: {

                    x: {
                        grid: {
                            display: false,
                        },
                        border: {
                            display: false,
                        }
                    },

                    y: {
                        beginAtZero: true,

                        grid: {
                            display: false,
                        },

                        border: {
                            display: false,
                        },

                        ticks: {
                            callback: function(value) {
                                if (value >= 1000000) {
                                    return (value / 1000000).toFixed(1) + "M";
                                }
                                if (value >= 1000) {
                                    return (value / 1000).toFixed(0) + "K";
                                }
                                return value;
                            }
                        }
                    }
                }
            }
        });
    }

    renderInvoiceStatusChart() {

        const data = this.state.dashboard_data.charts.invoice_status;

        const canvas = document.getElementById(
            "invoiceStatusChart"
        );

        if (!canvas || !data) {
            return;
        }

        const totalAmount =
            this.state.dashboard_data.kpis.invoice_total_amount || 0;
        const currency =
            this.state.dashboard_data.currency.symbol || ""

        new Chart(canvas, {
            type: "doughnut",

            data: {
                labels: [
                    "Paid",
                    "Partial",
                    "Unpaid",
                    "Overdue"
                ],

                datasets: [{
                    data: [
                        data.paid,
                        data.partial,
                        data.unpaid,
                        data.overdue
                    ],

                    backgroundColor: [
                        "#16A34A", // Green - Paid
                        "#FACC15", // Amber/Yellow - Partial
                        "#FB923C", // Orange - Unpaid
                        "#DC2626"  // Red - Overdue
                    ],

                    borderWidth: 0
                }]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,

                cutout: "70%",

                plugins: {
                    legend: {
                        position: "right",
                        labels: {
                            boxWidth: 15,
                            boxHeight: 15,
                        }
                    }
                }
            },

            plugins: [{
                    id: "centerText",

                    afterDraw(chart) {

                        const {
                            ctx,
                            chartArea: {
                                left,
                                right,
                                top,
                                bottom
                            }
                        } = chart;

                        const x = (left + right) / 2;
                        const y = (top + bottom) / 2;

                        ctx.save();

                        ctx.textAlign = "center";

                        ctx.fillStyle = "#111827";
                        ctx.font = "bold 18px Arial";

                        ctx.fillText(
                            `${currency}${totalAmount.toLocaleString()}`,
                            x,
                            y - 5
                        );

                        ctx.fillStyle = "#6B7280";
                        ctx.font = "12px Arial";

                        ctx.fillText(
                            "Total",
                            x,
                            y + 18
                        );

                        ctx.restore();
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                return currency + context.raw.toLocaleString();
                            }
                        }
                    }
                }]
            });
    }

    renderTopProductsChart() {

        const allData =
            this.state.dashboard_data.charts.top_products;

        const canvas =
            document.getElementById("topProductsChart");

        if (!canvas || !allData) {
            return;
        }

        const pageSize = this.topProductsPageSize;
        const start = this.state.topProductsPage * pageSize;
        const chartData = allData.slice(start, start + pageSize);

        const labels = chartData.map(item => {
            const name = item.product || "";

            return name.length > 15
                ? name.match(/.{1,15}/g)
                : name;
        });

        const sales = chartData.map(
            item => item.sales
        );

        const formatAmount = (value) => {
            if (value >= 1000000) {
                return (value / 1000000).toFixed(1) + "M";
            }
            if (value >= 1000) {
                return (value / 1000).toFixed(1) + "K";
            }
            return Number(value).toLocaleString(undefined, {
                minimumFractionDigits: 0,
                maximumFractionDigits: 2,
            });
        };

        const globalMax = Math.max(
            ...allData.map(item => item.sales),
            0
        );

        if (this.topProductsChartInstance) {
            this.topProductsChartInstance.destroy();
        }

        this.topProductsChartInstance = new Chart(canvas, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    label: "Sales",
                    data: sales,
                    backgroundColor: "#3B82F6",
                    maxBarThickness: 25,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: {
                        top: 25,
                        right: 10,
                        bottom: 10,
                        left: 10,
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return formatAmount(context.raw);
                            }
                        }
                    }
                },
               scales: {
                   x: {
                       grid: {
                           display: false,
                       },
                       border: {
                           display: false,
                       },
                       ticks: {
                           autoSkip: false,
                           maxRotation: 0,
                           minRotation: 0,
                           padding: 8,
                           font: {
                               size: 11,
                           }
                       }
                   },

                   y: {
                       beginAtZero: true,

                       grid: {
                           display: false,
                       },

                       border: {
                           display: false,
                       },

                       ticks: {
                           callback: function(value) {
                               return formatAmount(value);
                           }
                       }
                   }
               }
            }
        });
    }

    renderTopCustomersChart() {

        const allData =
            this.state.dashboard_data.charts.top_customers;

        const canvas =
            document.getElementById("topCustomersChart");

        if (!canvas || !allData) {
            return;
        }

        // NEW: slice data for current page
        const pageSize = this.topCustomersPageSize;
        const start = this.state.topCustomersPage * pageSize;
        const chartData = allData.slice(start, start + pageSize);

        const labels = chartData.map(
            item => item.customer
        );

        const sales = chartData.map(
            item => item.sales
        );

        const formatAmount = (value) => {
            if (value >= 1000000) {
                return (value / 1000000).toFixed(1) + "M";
            }
            if (value >= 1000) {
                return (value / 1000).toFixed(1) + "K";
            }
            return value.toString();
        };

        // NEW: destroy previous instance to avoid duplicate charts
        if (this.topCustomersChartInstance) {
            this.topCustomersChartInstance.destroy();
        }

        this.topCustomersChartInstance = new Chart(canvas, {
            type: "bar",
            data: {
                labels: labels,
                datasets: [{
                    data: sales,
                    backgroundColor: "#7367F0",
                    borderRadius: 4,
                    barThickness: 12,
                }]
            },
            options: {
                indexAxis: "y",
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: { right: 50 }
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.raw.toLocaleString();
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        display: false,
                        grid: { display: false },
                        border: { display: false }
                    },
                    y: {
                        grid: { display: false },
                        border: { display: false },
                        ticks: { font: { size: 12 } }
                    }
                }
            },
            plugins: [{
                id: "customerValueLabels",
                afterDatasetsDraw(chart) {
                    const { ctx } = chart;
                    ctx.save();
                    chart.getDatasetMeta(0).data.forEach(
                        (bar, index) => {
                            const value = sales[index];
                            ctx.fillStyle = "#374151";
                            ctx.font = "12px Arial";
                            ctx.fillText(
                                formatAmount(value),
                                bar.x + 10,
                                bar.y + 4
                            );
                        }
                    );
                    ctx.restore();
                }
            }]
        });
    }

    renderCityQuantityChart() {

        const allData = this.state.dashboard_data.charts.city_quantity;
        const canvas = document.getElementById("cityQuantityChart");

        if (!canvas || !allData) {
            return;
        }

        const pageSize = this.cityQuantityPageSize;
        const start = this.state.cityQuantityPage * pageSize;

        const chartData = allData.slice(start, start + pageSize);

        const labels = chartData.map(item => item.city);
        const quantities = chartData.map(item => item.qty);

        if (this.cityQuantityChartInstance) {
            this.cityQuantityChartInstance.destroy();
        }

        this.cityQuantityChartInstance = new Chart(canvas, {
            type: "line",

            data: {
                labels: labels,
                datasets: [{
                    label: "Quantity Sold",
                    data: quantities,

                    borderColor: "#2563EB",
                    backgroundColor: "rgba(37, 99, 235, 0.15)",

                    fill: true,
                    tension: 0.4,

                    pointRadius: 5,
                    pointHoverRadius: 7,
                    pointBackgroundColor: "#06B6D4",
                    pointBorderColor: "#ffffff",
                    pointBorderWidth: 2,
                }]
            },

            options: {
                responsive: true,
                maintainAspectRatio: false,

                plugins: {
                    legend: {
                        display: true,
                        position: "top",
                    },

                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `Qty Sold: ${context.raw}`;
                            }
                        }
                    }
                },

                scales: {
                    x: {
                        grid: {
                            display: false,
                        },
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45,
                        }
                    },

                    y: {
                        beginAtZero: true,

                        title: {
                            display: true,
                            text: "Quantity Sold",
                        }
                    }
                }
            }
        });
    }

    renderDeliveryStatusChart() {

        const chartData =
            this.state.dashboard_data.charts.delivery_status;
        const canvas =
            document.getElementById("deliveryStatusChart");
        if (!canvas || !chartData) {
            return;
        }

        const labels = chartData.map(
            item => item.status
        );
        const counts = chartData.map(
            item => item.count
        );

        const totalDeliveries = counts.reduce(
            (sum, count) => sum + count,
            0
        );

        if (this.deliveryChartInstance) {
            this.deliveryChartInstance.destroy();
        }

        this.deliveryChartInstance = new Chart(canvas, {
            type: "doughnut",

            data: {

                labels: [
                    "Fully Delivered",
                    "Partially Delivered",
                    "Pending Delivery",
                    "Cancelled"
                ],
                datasets: [{
                    data: counts,
                    backgroundColor: [
                        "#6B8E4E", 
                        "#C9885A",
                        "#D4A437", 
                        "#7B5D4B" 
                    ],
                    borderWidth: 1,
                }]
            },
            options: {
                cutout: "70%",
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: "right",
                        labels: {
                            boxWidth: 15,
                            boxHeight: 15,
                        }
                    }
                }
            },
            plugins: [{
                    id: "centerText",
                    afterDraw(chart) {

                        const { ctx } = chart;

                        const meta = chart.getDatasetMeta(0);

                        if (!meta.data.length) {
                            return;
                        }

                        const centerX = meta.data[0].x;
                        const centerY = meta.data[0].y;

                        ctx.save();

                        ctx.textAlign = "center";
                        ctx.textBaseline = "middle";

                        ctx.font = "bold 22px Arial";
                        ctx.fillStyle = "#111827";
                        ctx.fillText(
                            totalDeliveries,
                            centerX,
                            centerY - 10
                        );

                        ctx.font = "13px Arial";
                        ctx.fillStyle = "#6B7280";
                        ctx.fillText(
                            "Orders",
                            centerX,
                            centerY + 12
                        );

                        ctx.restore();
                    }
                }
            ],
        });
    }

    renderCarrierShippingChart() {

        const allData = this.state.dashboard_data.charts.carrier_shipping;

        const canvas = document.getElementById("carrierShippingChart");

        if (!canvas || !allData) {
            return;
        }

        const pageSize = this.carrierShippingPageSize;
        const start = this.state.carrierShippingPage * pageSize;
        const chartData = allData.slice(start, start + pageSize);

        const labels = chartData.map(item => item.carrier);
        const costs = chartData.map(item => item.cost);

        const formatAmount = (value) => {
            if (value >= 1000000) {
                return (value / 1000000).toFixed(1) + "M";
            }
            if (value >= 1000) {
                return (value / 1000).toFixed(1) + "K";
            }
            return Number(value).toLocaleString(undefined, {
                minimumFractionDigits: 0,
                maximumFractionDigits: 2,
            });
        };

        // Fixed scale across all pages
        const allCosts = allData.map(item => item.cost);
        const globalMax = Math.max(...allCosts, 0);

        if (this.carrierShippingChartInstance) {
            this.carrierShippingChartInstance.destroy();
        }

        this.carrierShippingChartInstance = new Chart(canvas, {
            type: "line",
            data: {
                labels: labels,
                datasets: [{
                    label: "Shipping Cost",
                    data: costs,

                    borderColor: "#0F766E",
                    backgroundColor: "rgba(15, 118, 110, 0.15)",

                    fill: true,
                    tension: 0.4,

                    pointRadius: 5,
                    pointHoverRadius: 7,

                    pointBackgroundColor: "#10B981",
                    pointBorderColor: "#FFFFFF",
                    pointBorderWidth: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: globalMax + (globalMax * 0.1 || 1),
                        ticks: {
                            callback: value => formatAmount(value)
                        }
                    }
                }
            }
        });
    }
}

SalesDashboard.template = "sales_dashboard_vts.SalesDashboard";

registry.category("actions").add(
    "sales_dashboard_tag",
    SalesDashboard
);