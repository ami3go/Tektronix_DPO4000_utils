# Troubleshooting

## No VISA resources found

Check that a VISA runtime is installed and that the oscilloscope is visible to that runtime. You can also enter the VISA resource manually in the Connection tab.

## GUI opens but cannot connect

Use **Test IDN** first. If it fails, verify the resource string and timeout value.

## Screenshot preview says the image cannot be identified

The active GUI extracts the PNG payload from Tektronix hardcopy data and trims SCPI block headers. If the issue persists, try VXI-11 instead of raw socket, increase timeout, and confirm the scope is returning PNG hardcopy data.

## Trigger does not re-arm after screen capture

Enable the trigger re-arm option below the preview. The GUI can re-write trigger/acquisition state after image capture as a practical workaround.
