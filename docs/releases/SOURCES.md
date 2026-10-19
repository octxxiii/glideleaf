# Source and license information for v0.2.0-alpha.1

The portable app is built from the [Glideleaf v0.2.0-alpha.1 tag](https://github.com/octxxiii/glideleaf/tree/v0.2.0-alpha.1).
Its `_internal/LICENSE` and `_internal/THIRD_PARTY_NOTICES.md` identify the
project and dependency licenses. `_internal/licenses/dependencies.json` records
the bundled Python distributions and their collected license files.

The separate `Glideleaf-0.2.0-alpha.1-lgpl-sources.zip` release asset contains:

| Bundled component | Corresponding source |
| --- | --- |
| libusb native DLL, 1.0.26 | [libusb v1.0.26](https://github.com/libusb/libusb/tree/v1.0.26) |
| libusb-package 1.0.26.4 | [libusb-package v1.0.26.4](https://github.com/pyocd/libusb-package/tree/v1.0.26.4); its libusb submodule source is supplied separately above |
| libusb1 Python wrapper 3.4.0 | [libusb1 3.4.0 source distribution](https://pypi.org/project/libusb1/3.4.0/#files) |
| pystray 0.19.5 | [pystray v0.19.5](https://github.com/moses-palmer/pystray/tree/v0.19.5) |

These libraries are not modified by Glideleaf. The external libusb DLL remains
a separate file under `_internal`, and the [application source and build
instructions](https://github.com/octxxiii/glideleaf/tree/v0.2.0-alpha.1) are
available to rebuild with modified Python dependencies. The source archive is
provided alongside the binary to make the relevant LGPL component code
available at the same release URL. This document records distribution inputs;
it does not claim a legal certification.
