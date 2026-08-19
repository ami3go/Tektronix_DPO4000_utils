from  tektronix_utils import DPO4054
if __name__ == "__main__":
    # Example usage
    scope = DPO4054()

    try:
        scope.apply_scope_settings(
            "ppe41c_hv_pulse.json",
            wait_complete=True,
            opc_timeout_ms=60000,
        )
    finally:
        scope.disconnect()