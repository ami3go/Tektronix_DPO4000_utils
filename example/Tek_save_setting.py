import  tektronix_utils
if __name__ == "__main__":
    # Example usage
    scope = tektronix_utils.DPO4054()

    try:
        scope.connect()
        scope.save_scope_settings("ppe41c_hv_pulse.json")
    finally:
        scope.disconnect()