def human_size(size_bytes: int) -> str:
    """Convert a byte count into a human-readable string (e.g. '1.4 GB')."""
    if not size_bytes or size_bytes < 0:
        return "Unknown size"
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    value = float(size_bytes)
    for unit in units[:-1]:
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} {units[-1]}"
