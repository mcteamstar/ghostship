# Spec Delta

## REMOVED Requirements

### Requirement: privacy template dispatches a single Banshee privacy reviewer
**Reason**: Privacy scanning is part of the independent-review workflow, not a standalone Captain order.
**Migration**: Use the privacy reviewer included in the `independent-review` (`indy`) order.

### Requirement: privacy Banshee scans for internal infrastructure references
**Reason**: This requirement exists only to define the standalone privacy Captain order; the same scan remains specified as an independent-review shard.
**Migration**: Use the privacy-review requirement in `captain/independent-review`.

### Requirement: privacy standalone template mails findings to admiral@localhost and self-cancels
**Reason**: Standalone privacy orders are removed; Indy continues to consolidate privacy findings with the other review reports.
**Migration**: Run `independent-review` (`indy`) to receive privacy findings in its consolidated report.
