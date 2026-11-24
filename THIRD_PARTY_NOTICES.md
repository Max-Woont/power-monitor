# Third-party notices

Power Monitor is licensed under the GNU General Public License v3.0 or later (see [LICENSE](LICENSE)).
It uses the third-party components and data listed below. Their licenses apply to those components only.
Copies of the license texts that are not linked to an upstream page are in the [`licenses/`](licenses) folder.

## Data

### outages-data

- Source: outages-data, https://github.com/mrkaktuz/outages-data
- License: [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
- Used: the app downloads the published JSON schedules (`data` branch) at runtime and caches them locally.
  The data is not stored in this repository.
- Changes: the app parses the schedules, merges adjacent intervals, may treat "possible" intervals as outages
  (a user setting) and displays the result. The original data is not modified at the source.
- Only the data is used. The outages-data collector code and web page are under a separate,
  non-free license and are **not** used or copied by this project.
- The schedules originally come from the regional power distribution companies (DTEK, Zhytomyroblenergo,
  Mykolaivoblenergo). Power Monitor is not affiliated with them or with outages-data.

## Libraries bundled into `PowerMonitor.exe`

| Component | License | Source |
|---|---|---|
| PySide6, Shiboken6 (Qt for Python) | LGPL-3.0 ([text](licenses/LGPL-3.0.txt), which builds on GPL-3.0 in [LICENSE](LICENSE)) | https://code.qt.io/cgit/pyside/pyside-setup.git |
| Qt 6 libraries | LGPL-3.0 | https://download.qt.io/official_releases/qt/ |
| requests | Apache-2.0 ([text](licenses/Apache-2.0.txt)) | https://github.com/psf/requests |
| urllib3 | MIT | https://github.com/urllib3/urllib3 |
| idna | BSD-3-Clause | https://github.com/kjd/idna |
| charset-normalizer | MIT | https://github.com/jawah/charset_normalizer |
| certifi | MPL-2.0 | https://github.com/certifi/python-certifi |
| Python runtime | PSF-2.0 | https://www.python.org/ |

### Replacing the Qt / PySide6 libraries (LGPL-3.0)

The complete source code of Power Monitor is available in this repository. To use a modified or different
version of PySide6/Qt, install it in a Python environment and run the app from source (`python main.py`),
or rebuild the executable with `pyinstaller --noconfirm PowerMonitor.spec`.
