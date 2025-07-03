odoo.define('financial_reconciliation.reconciliation', function (require) {
    "use strict";

    const { Component, useState, onWillStart } = owl;
    const { useModel } = require('web.Model');
    const AbstractAction = require('web.AbstractAction');
    const core = require('web.core');
    const rpc = require('web.rpc');
    const session = require('web.session');
    const utils = require('web.utils');

    // Componente para la vista Kanban
    class ReconciliationKanbanRenderer extends Component {
        setup() {
            this.state = useState({
                records: [],
                loading: true,
                colors: {
                    'draft': '#f0f0f0',
                    'review': '#d9edf7',
                    'validated': '#dff0d8',
                    'cancelled': '#f2dede'
                }
            });
            
            onWillStart(async () => {
                await this.loadRecords();
            });
        }

        async loadRecords() {
            try {
                const records = await this.props.model.load();
                this.state.records = records;
                this.state.loading = false;
            } catch (error) {
                console.error("Error loading records:", error);
                this.state.loading = false;
            }
        }

        getColor(state) {
            return this.state.colors[state] || '#ffffff';
        }

        openRecord(recordId) {
            this.do_action({
                type: 'ir.actions.act_window',
                res_model: 'financial.reconciliation',
                res_id: recordId,
                views: [[false, 'form']],
                target: 'current'
            });
        }
    }
    ReconciliationKanbanRenderer.template = 'financial_reconciliation.KanbanRenderer';

    // Componente para el OCR en tiempo real
    class OCRPreview extends Component {
        setup() {
            this.state = useState({
                previewText: '',
                processing: false
            });
        }

        async processOCR() {
            this.state.processing = true;
            try {
                const imageData = this.props.imageData;
                if (!imageData) {
                    this.state.previewText = "No hay imagen para procesar";
                    return;
                }

                const result = await rpc.query({
                    route: '/financial_reconciliation/process_ocr',
                    params: { image_data: imageData }
                });

                this.state.previewText = result || "No se pudo extraer texto";
            } catch (error) {
                console.error("OCR Error:", error);
                this.state.previewText = "Error en el procesamiento OCR";
            } finally {
                this.state.processing = false;
            }
        }
    }
    OCRPreview.template = 'financial_reconciliation.OCRPreview';
    OCRPreview.props = ['imageData'];

    // Componente principal para acciones personalizadas
    class ReconciliationController extends AbstractAction {
        async willStart() {
            this.model = new useModel('financial.reconciliation');
            this.state = useState({
                searchTerm: '',
                searchType: 'identification',
                searchResults: []
            });
        }

        async searchExternal() {
            try {
                const results = await rpc.query({
                    model: 'financial.reconciliation',
                    method: 'action_search_external',
                    args: [[], {
                        term: this.state.searchTerm,
                        type: this.state.searchType
                    }]
                });
                
                this.state.searchResults = results || [];
            } catch (error) {
                console.error("Search Error:", error);
                this.state.searchResults = [];
                this.displayNotification({
                    title: "Error",
                    message: "Error en la búsqueda externa",
                    type: 'danger'
                });
            }
        }

        clearSearch() {
            this.state.searchTerm = '';
            this.state.searchResults = [];
        }

        displayNotification(params) {
            this.do_action({
                type: 'ir.actions.client',
                name: 'Display Notification',
                tag: 'display_notification',
                params: params
            });
        }
    }
    ReconciliationController.components = { ReconciliationKanbanRenderer, OCRPreview };
    ReconciliationController.template = 'financial_reconciliation.MainTemplate';

    // Registro de componentes
    core.action_registry.add('reconciliation_controller', ReconciliationController);
    core.action_registry.add('reconciliation_kanban', ReconciliationKanbanRenderer);

    return {
        ReconciliationController,
        ReconciliationKanbanRenderer,
        OCRPreview
    };
});