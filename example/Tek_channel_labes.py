from tektronix_utils import DPO4054
if __name__ == "__main__":
    # Example usage
    scope = DPO4054()

    try:
        scope.set_channel_label(1, "PWR+")
        scope.set_channel_label(2, "S17")
        scope.set_channel_label(3, "S16")
        scope.set_channel_label(4, "S15")
        print(1," : ",scope.get_channel_label(1))
        print(2," : ",scope.get_channel_label(2))
        print(3," : ",scope.get_channel_label(3))
        print(4," : ",scope.get_channel_label(4))
    finally:
        scope.disconnect()