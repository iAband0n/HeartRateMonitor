import asyncio
import sys


async def main() -> None:
    from bleak import BleakScanner

    found = {}

    def cb(device, adv):
        found[device.address] = (device.name or adv.local_name, adv.rssi, adv.service_uuids)
        print("FOUND", device.address, device.name, adv.rssi, adv.service_uuids, flush=True)

    print("starting scan", flush=True)
    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    await asyncio.sleep(8)
    await scanner.stop()
    print("scan done", len(found), flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("SCAN ERROR", type(exc).__name__, exc, flush=True)
        sys.exit(1)
