# Terms of Use and Legal Notice

_Last updated: November 9, 2026_

These terms explain the legal position of **os-lab** (the labs, `labctl`, the
installers, the web console and the dashboard in this repository, together the
"Software") and your responsibilities when you run it. They are a notice and a
statement of conditions for using the project's name, documentation and
support channels. **They do not change the
[Apache License 2.0](../../LICENSE)**, which is the only licence that governs
the source code.

## 1. What os-lab is

os-lab is open-source software that you download and run on your own computer
or server. It builds isolated security labs (an Android analysis stack, Windows,
Linux and macOS/iOS virtual machines) with Docker and KVM, and a web console
that controls them. Source Lab adds local static source/package analysis,
structural maps and explicitly invoked repository/evidence workflows; it does
not require a guest for static analysis.

- There is **no hosted service**. The project does not operate servers that
  receive your data, and the web console listens only on `127.0.0.1` on the
  machine where you start it.
- **You are the operator.** Whoever installs and runs a copy of the Software
  decides what it is used for and is responsible for that use, for the systems
  and data it touches, and for complying with the law.

## 2. Licence

The Software is licensed under the Apache License, Version 2.0. You may use,
modify and distribute it under that licence, including its conditions on notices
and attribution. Third-party components keep their own licences; see
[Third-Party Notices](THIRD_PARTY_NOTICES.md).

## 3. Lawful and authorized use

The labs contain offensive-security tooling: traffic interception (mitmproxy),
runtime instrumentation (Frida), APK patching, IPC fuzzing, decompilation and
port scanning. Using such tools against systems, applications or data without
permission can be a criminal offence, including under Articles 243–244 of the
Turkish Penal Code (No. 5237), the U.S. Computer Fraud and Abuse Act, the U.K.
Computer Misuse Act 1990 and equivalent laws elsewhere.

Only analyse applications, devices, networks and services that you own or that
you are expressly authorized in writing to test, and only within that scope. The
[Acceptable Use Policy](ACCEPTABLE_USE.md) sets out what the project supports.

## 4. Operating-system and software licences

The labs automate the installation of software that the project does not own or
licence to you:

- **Windows** (`win-lab`, via `dockurr/windows`): you must hold a valid Windows
  licence for every installation and comply with the Microsoft Software
  Licence Terms. Evaluation media is limited to evaluation use.
- **macOS** (`ios-lab`, via `dockurr/macos`): Apple's macOS licence agreement
  permits virtualization of macOS only on Apple-branded hardware. Running the
  macOS VM on other hardware may breach that licence; on such hosts use the
  native macOS path or a Mac. Xcode and the iOS Simulator are governed by
  Apple's own terms.
- **Android emulator images, SDK tools and Google Play services** are governed
  by Google's Android SDK terms.
- **Container images and tools** (Docker-Android, MobSF, mitmproxy, JADX, Frida
  and others) are governed by their own licences.

You are responsible for obtaining and complying with these licences. Nothing in
the Software or its documentation grants you rights to third-party software.

## 5. Data you process with the labs

When you intercept traffic, dump application sandboxes or analyse apps, you may
process personal data and confidential information belonging to others. For that
processing you are the controller: you need a lawful basis and must meet your
obligations under applicable law, including the Turkish Personal Data
Protection Law No. 6698 (KVKK) and the EU General Data Protection Regulation
(GDPR) where they apply. Keep captures and artifacts only as long as needed,
protect them, and delete them when the engagement ends.

## 6. Isolation and safety

Guests can run untrusted or malicious software. Keep labs isolated from
production networks and sensitive data, do not expose lab ports or the web
console to untrusted networks, and keep the host patched. Some actions (for
example **Install dependencies**) install packages, change user groups and
system services, and require administrator rights: review the preview the
console shows before confirming.

## 7. No warranty

As stated in section 7 of the Apache License, the Software is provided on an
**"AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND**, express or
implied, including warranties of title, non-infringement, merchantability or
fitness for a particular purpose. Findings, scores and reports produced by the
labs are automated and can be incomplete or wrong; they are not a security
audit, certification or legal advice.

## 8. Limitation of liability

As stated in section 8 of the Apache License, and to the extent permitted by
applicable law, no contributor is liable to you for damages of any kind,
including direct, indirect, special, incidental or consequential damages,
arising from the use of or inability to use the Software, including loss of
data, systems or goodwill, or damage to third parties caused by your use.
Liability that cannot be excluded by law, such as for intent or gross
negligence, is not excluded.

## 9. Trademarks

Windows is a trademark of Microsoft Corporation; Apple, macOS, iOS and Xcode
are trademarks of Apple Inc.; Android and Google Play are trademarks of Google
LLC; Docker is a trademark of Docker, Inc. Other names belong to their owners.
os-lab is an independent project and is not affiliated with, endorsed or
sponsored by any of them.

## 10. Changes and contact

These terms may be updated; the date above shows the current version, and the
history is in this repository. Questions go to the project's
[GitHub issues](https://github.com/keyvanarasteh/os-lab/issues); security
reports follow [SECURITY.md](../../SECURITY.md).
