/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, onWillStart, onMounted, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

class ReconciliationDashboard extends Component {
    static template = "financial_reconciliation.ReconciliationDashboard";

    setup() {
        this.orm = useService("orm");
        this.chartRef = useRef("chart_container");
        this.reconciliationData = {};

        onWillStart(async () => {
            const data = await this.orm.searchRead(
                "financial.reconciliation",
                [],
                ["state", "amount"],
            );
            this.reconciliationData = this.processData(data);
        });

        onMounted(() => {
            this.renderChart();
        });
    }

    processData(data) {
        const states = {
            draft: { count: 0, label: "Borrador" },
            review: { count: 0, label: "En Revisión" },
            validated: { count: 0, label: "Validado" },
            cancelled: { count: 0, label: "Cancelado" },
        };
        data.forEach(rec => {
            if (rec.state in states) {
                states[rec.state].count++;
            }
        });
        return Object.keys(states).map(key => ({
            state: states[key].label,
            value: states[key].count,
        }));
    }

    renderChart() {
        const data = this.reconciliationData;
        const container = this.chartRef.el;
        if (!container) return;
        
        const margin = { top: 20, right: 20, bottom: 40, left: 40 };
        const width = container.clientWidth - margin.left - margin.right;
        const height = 400 - margin.top - margin.bottom;

        // Limpiar SVG anterior
        d3.select(container).select("svg").remove();

        const svg = d3.select(container).append("svg")
            .attr("width", width + margin.left + margin.right)
            .attr("height", height + margin.top + margin.bottom)
            .append("g")
            .attr("transform", `translate(${margin.left},${margin.top})`);

        const x = d3.scaleBand()
            .range([0, width])
            .padding(0.1)
            .domain(data.map(d => d.state));

        const y = d3.scaleLinear()
            .range([height, 0])
            .domain([0, d3.max(data, d => d.value) || 1]);

        svg.append("g")
            .attr("transform", `translate(0,${height})`)
            .call(d3.axisBottom(x))
            .selectAll("text")
            .attr("transform", "translate(-10,0)rotate(-45)")
            .style("text-anchor", "end");

        svg.append("g")
            .call(d3.axisLeft(y));

        svg.selectAll(".bar")
            .data(data)
            .enter().append("rect")
            .attr("class", "bar")
            .attr("x", d => x(d.state))
            .attr("width", x.bandwidth())
            .attr("y", d => y(d.value))
            .attr("height", d => height - y(d.value))
            .attr("fill", "#69b3a2");
    }
}

registry.category("actions").add("reconciliation_dashboard", ReconciliationDashboard);