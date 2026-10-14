# FedEx Address Wizard — Odoo 19 upgrade notes

## Diagnosis

`Model fedex.address.wizard has no table` indicates that Odoo sees the Python model but does not find its PostgreSQL table at the time of the check. Both address wizard classes are already correctly declared as `models.TransientModel`; their tables must still be initialized through the Odoo module installation/upgrade lifecycle. Both classes now explicitly set `_auto = True` for clarity (this is already the default). **This code change alone does not create database tables.**

## Required deployment

1. Back up the database and deploy this module to the Odoo 19 addons path.
2. Restart the Odoo server so the Python model definitions load.
3. Upgrade the installed `fedex_shipping_odoo_integration` module on the *affected database* from Apps, or use:

   `./odoo-bin -c /path/to/odoo.conf -d DATABASE -u fedex_shipping_odoo_integration --stop-after-init`

4. Restart Odoo again after the successful upgrade, if using the CLI.
5. Confirm both tables exist using PostgreSQL:

   `SELECT to_regclass('public.fedex_address_wizard'), to_regclass('public.fedex_address_wizard_line');`

If either is NULL after the upgrade, check the *full* Odoo install/upgrade traceback for an interrupted registry setup, module install state, bad addon path or conflicting model extension. Avoid manually creating ORM tables.

## Review / testing

- Verified both Python models are imported from the addon entry point.
- Confirmed both models extend TransientModel, and their view and security records are included in the manifest.
- Validated Python syntax and XML well-formedness statically.
- No running Odoo 19 server or database is attached, so live install, module upgrade, and FedEx API testing are **not** performed.

## Changes in 19.0.1.5

- Explicitly enable ORM table generation for both FedEx transient wizard classes.
- Handle a missing `messages` element from an address-validation response without a KeyError.
- Normalize the manifest encoding header; bump module version to 19.0.1.5.
