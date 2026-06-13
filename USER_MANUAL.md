# FluxPark User Manual

This manual explains how to use FluxPark from the perspective of an end user
— residents, committee members, security staff, office employees, and
managers. For developer/setup documentation, see [README.md](README.md).

## Table of Contents

1. [Getting Started](#getting-started)
2. [Choosing a Property Type & Role](#choosing-a-property-type--role)
3. [Dashboard](#dashboard)
4. [My Rooms (Multi-Property Membership)](#my-rooms-multi-property-membership)
5. [My Profile](#my-profile)
6. [Parking](#parking)
7. [Visitor Management](#visitor-management)
8. [Transport (Office)](#transport-office)
9. [Team / Members Directory](#team--members-directory)
10. [Invite Links](#invite-links)
11. [Payments](#payments)
12. [Notifications](#notifications)
13. [AI Assistant](#ai-assistant)
14. [Language](#language)
15. [FAQ / Troubleshooting](#faq--troubleshooting)

## Getting Started

### Sign Up

1. Open FluxPark in your browser.
2. On the **Sign Up** page, enter your name and phone number.
3. FluxPark sends a one-time password (OTP) to verify your phone number.

### Verify OTP

1. Enter the OTP you received on the **Verify OTP** page.
2. OTPs are valid for a limited time (5 minutes). If it expires, request a new
   one.
3. Once verified, your account is created and you're logged in.

## Choosing a Property Type & Role

After your first sign-in, FluxPark asks you to set up or join a property.

### Setting up a new property

- **Residential** (Apartment / Gated Community):
  - Enter the property name, address, number of units, and parking details.
  - You become the **Owner** (or **Committee**) for that property.
- **Office**:
  - Enter the office/building details and add one or more **companies**
    (sub-rooms) that operate within it, including their parking allocation.
  - You become a **Manager** for your company.

### Roles

| Property type | Roles available |
|---|---|
| Apartment / Gated Community | Owner, Tenant, Committee, Security |
| Office | Employee, Manager, Security |

- **Owner / Tenant**: residents with a parking slot and vehicle(s) registered
  to their unit.
- **Committee**: manages the residential property — parking layout, members,
  invite links, notifications, visitor approvals.
- **Manager**: manages a company within an office property — company parking
  allocation, team directory, invite links, transport requests.
- **Employee**: office staff with a parking slot/transport pass tied to their
  company.
- **Security**: staff who scan QR codes for vehicle/visitor entry & exit, log
  visitors, and handle unexpected-visitor flows.

### Joining an existing property

If someone shares an **invite link** with you, open it while logged in (or
sign up first if you're new). You'll be guided through a role-specific form
(e.g. owner/tenant details, employee details) to complete your profile for
that property/company.

## Dashboard

After onboarding, your **Dashboard** is the home screen and adapts to your
role:

- **Owner / Tenant / Committee**: parking slot status, vehicle summary,
  notifications, and quick links to parking map/availability.
- **Employee / Manager**: company parking slot status, transport pass/request
  status, and (for managers) a team overview.
- **Security**: quick access to QR scanning, visitor logging, and
  unexpected-visitor handling for the property/company they're assigned to.

The sidebar navigation shows only the pages relevant to your current role.

## My Rooms (Multi-Property Membership)

A single FluxPark account can belong to **more than one property or
company** — for example, you might be a Tenant in one apartment and an
Employee at an office.

Open **My Rooms** from the sidebar to:

- See every property/company you're part of, with your role in each
  (e.g. "Owner", "Manager").
- See which one is **currently active** — this is the property/company whose
  data (parking, members, notifications, etc.) is shown across the app.
- **Switch** to a different room — click "Switch to this room" on any card to
  make it active.
- **Join another room** — paste an invite link or code you received, and
  follow the role-specific onboarding form for that property/company. If
  you're already a member of that property/company, FluxPark tells you and
  won't create a duplicate membership.

## My Profile

**My Profile** shows your personal details, your role, your registered
vehicle(s), and (where applicable) bank details for payouts. Some fields can
be edited directly; others (like your role) are fixed once set during
onboarding.

## Parking

### Parking Slots

- **Owner / Committee / Manager** can view and edit the parking layout for
  their property/company: slot numbers, floor assignment, and which
  resident/employee a slot is assigned to.
- Slot numbers are generated automatically when a property/company is set up,
  but can be adjusted afterwards from this page.
- For office properties, each company only sees and edits its **own** parking
  slots.

### Parking Map

A visual, floor-by-floor map of all parking slots showing live status
(vacant, occupied, reserved) at a glance.

### Parking Availability

A simple live view of how many slots are currently vacant vs. occupied —
useful for security staff and residents/employees checking for free spots.

## Visitor Management

### Visitor Pass / Visitor Request

Residents and employees can:

- Generate a **Visitor Pass** (with a QR code) to share with an expected
  guest, so security can quickly verify and log their entry/exit.
- Submit a **Visitor Request** ahead of time for approval (residential
  committees may need to approve certain visitor types).

### Visitor Log (Security)

Security staff use the **Visitor Log** to:

- Scan visitor QR passes for entry/exit.
- See a running log of all visitor activity, with CSV export for record
  keeping.

### Unexpected Visitor

If someone arrives without a pre-issued pass, security can log them through
the **Unexpected Visitor** flow, capturing their details and notifying the
relevant resident/employee/host.

## Transport (Office)

Office employees can:

- Submit a **Transport Request** (e.g. for company-arranged transport),
  specifying shift timing and pickup/drop details.
- View their **Transport Pass** once a request is approved, including any QR
  code needed for verification.

Security staff can verify transport passes from the **Security Transport**
page.

## Team / Members Directory

- **Committee** (residential) sees all owners/tenants/committee members for
  their property.
- **Manager** (office) sees their company's employees and managers only —
  other companies' staff are not visible.
- From here, authorized roles (Committee/Manager) can remove a member if they
  leave the property/company.

## Invite Links

Committee members and managers can generate **invite links** to onboard new
residents, employees, or managers:

- Share the link with the person you want to invite.
- When they open it (and sign up/log in), they're guided through the correct
  role form for your property/company.
- If they're already a member of that property/company, they'll see a
  friendly "you're already part of this" message instead of a duplicate
  signup.

## Payments

The **Payments** page tracks transactions related to your property/company
(e.g. dues, payouts), giving residents, committee members, and managers a
record of payment activity.

## Notifications

All roles have a **Notifications** centre showing property/company
announcements, visitor/transport updates, and other alerts. Unread
notifications are highlighted.

## AI Assistant

FluxPark includes an in-app **AI Assistant** to help answer questions about
your property, parking, or how to use the app.

### AI Settings

Each user can configure their own AI provider from **AI Settings**:

- **Ollama** (local/self-hosted): point to your Ollama server (default
  `http://localhost:11434`) and choose a model (e.g. `llama3.2`).
- **BYOK** (Bring Your Own Key): provide a hosted provider's base URL, API
  key, and model name (e.g. an OpenAI-compatible endpoint).

These settings are stored against your account and used only for your own AI
Assistant conversations.

### Using the Assistant

Open **AI Assistant** from the sidebar and type your question. Your
conversation history is saved so you can continue where you left off.

## Language

FluxPark is available in **English**, **Hindi (हिन्दी)**, and **Telugu
(తెలుగు)**. Use the language switcher (usually in the header/sidebar) to
change the display language at any time — your selection applies across the
whole app.

## FAQ / Troubleshooting

**I didn't receive an OTP.**
Wait a minute and request a new one. Make sure the phone number you entered
is correct.

**My OTP expired.**
OTPs are valid for 5 minutes. Request a new OTP and try again.

**I can't see a page that another resident/employee has access to.**
Navigation is role-based — some pages (e.g. Parking Slots editing, Invite
Links, Members) are only available to Owner/Committee (residential) or
Manager (office) roles.

**I'm part of two properties — how do I switch between them?**
Use **My Rooms** in the sidebar. See
[My Rooms (Multi-Property Membership)](#my-rooms-multi-property-membership).

**An invite link says "you're already part of this".**
This means your account already has a role in that property/company —
FluxPark won't create a duplicate. Use **My Rooms** to switch to it.

**I forgot which property is currently active.**
Check **My Rooms** — the property/company marked "Currently active" is the
one whose data you're currently viewing across the app.
