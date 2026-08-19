import  tektronix_utils
if __name__ == "__main__":
    # Example usage
    scope = tektronix_utils.DPO4054()

    try:
        scope.connect()
        # scope.save_all_channels_to_single_csv("waveform_all_channels.csv")
        # scope.set_channel_label(1, "Vc_galaxy")
        # scope.set_channel_label(2, "Vc_mcc")
        # scope.set_channel_label(3, "V_in")
        # scope.set_channel_label(4, "")
        # scope.set_channel_label(3, "VREG-5V")
        # scope.set_channel_label(4, "SW_NODE")
        scope.save_all_channels_to_single_csv("mcc_vs_vishay_llf.csv")

    finally:
        scope.disconnect()