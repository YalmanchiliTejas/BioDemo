import { Activity, BookOpen, Boxes, Database, Factory, FlaskConical, Globe, ShieldCheck, Wrench, type LucideIcon } from 'lucide-react';

export const FAMILIES: Record<string, { title: string; description: string; icon: LucideIcon }> = {
    MES: { title: 'Manufacturing', description: 'Batch records, orders & production events', icon: Factory },
    LIMS: { title: 'Laboratory', description: 'Samples, tests & laboratory results', icon: FlaskConical },
    QMS: { title: 'Quality', description: 'Deviations, CAPAs & quality records', icon: ShieldCheck },
    HISTORIAN: { title: 'Process measurements', description: 'Historian tags & equipment signals', icon: Activity },
    ERP: { title: 'Materials', description: 'Materials, lots & resource planning', icon: Boxes },
    ELN: { title: 'Lab notebooks', description: 'Experiments & research context', icon: BookOpen },
    CMMS: { title: 'Maintenance', description: 'Equipment & maintenance work orders', icon: Wrench },
    WMS: { title: 'Warehouse', description: 'Inventory, storage locations & stock', icon: Database },
};

export const PRODUCT_ICONS: Record<string, LucideIcon> = {
    veeva_vault: ShieldCheck, pi_web_api: Activity, snowflake: Database, databricks: Database, benchling: BookOpen, rest_api: Globe,
};

const FIELD_LABELS: Record<string, string> = {
    order_id: 'Order number', batch_id: 'Batch', status: 'Status', equipment_id: 'Equipment', product: 'Product',
    sample_id: 'Sample', test: 'Test', value: 'Value', unit: 'Unit', case_id: 'Record number', record_type: 'Record type',
    description: 'Description', owner: 'Owner', lot_number: 'Lot number', material_code: 'Material code', expiry: 'Expiry date',
    qty: 'Quantity', uom: 'Unit of measure', tag: 'Tag', quality: 'Data quality', experiment_id: 'Experiment', title: 'Title',
    work_order: 'Work order', location: 'Location', elapsed_h: 'Elapsed time (h)',
};

export const fieldLabel = (canonical: string) => FIELD_LABELS[canonical] ?? canonical.replaceAll('_', ' ');
