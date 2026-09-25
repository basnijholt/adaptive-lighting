## REMOVED Requirements

### Requirement: YAML-managed config entries cannot be edited via the options dialog

**Reason**: The fork no longer imports YAML at all, so no entry can be YAML-managed.
**Migration**: None. Configure profiles in the UI; a leftover `adaptive_lighting:` block only produces HA's standard UI-only warning.
