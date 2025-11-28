from . import models


def uninstall_hook(env):
    """
    Clean up stored computed fields when module is uninstalled.

    This prevents orphaned database columns and ensures clean uninstallation.
    All computed fields with store=True create database columns that need cleanup.
    """
    # List of computed stored fields to remove
    fields_to_remove = [
        'customer_invoiced_amount',
        'customer_paid_amount',
        'customer_outstanding_amount',
        'customer_skonto_taken',
        'vendor_bills_total',
        'vendor_skonto_received',
        'total_costs_net',
        'total_costs_with_tax',
        'profit_loss',
        'negative_difference',
        'total_hours_booked',
        'labor_costs',
        'project_id_display',
        'client_name',
        'head_of_project'
    ]

    # Build DROP COLUMN statements
    drop_statements = ', '.join([f'DROP COLUMN IF EXISTS {field}' for field in fields_to_remove])

    # Execute cleanup
    try:
        env.cr.execute(f"""
            ALTER TABLE project_project
            {drop_statements}
        """)
        env.cr.commit()
    except Exception as e:
        # Log but don't fail - some columns might not exist
        import logging
        _logger = logging.getLogger(__name__)
        _logger.warning(f"Error during uninstall cleanup: {e}")