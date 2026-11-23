# UX review checklist

Go through each scenario first, then each screen. Every problem becomes an `issues` entry with a severity:
- **S1** blocks the task or loses data
- **S2** major friction or missing recovery
- **S3** confusing or inconsistent
- **S4** polish

## Task completion (`flow`)
- Can the main journey finish? Count the steps. Is any step unnecessary or repeated?
- Does each screen make the next action obvious? Is there exactly one primary action?
- Is the user asked for information before it is needed?

## Navigation (`navigation`)
- Can every screen be left with back or close? Where does back go, and is that what the user expects?
- After leaving and returning, are tab position, scroll position, filters and entered values kept?
- Can deep links and notifications land on the right screen, and what happens when the target no longer exists?

## Feedback (`feedback`)
- Is loading or progress visible for anything slower than an instant?
- Is submitting twice prevented? Is the button locked while sending, and are duplicates detected?
- Does a success screen say what happens next, and when?

## Error recovery (`error-recovery`)
- Are validation messages specific, shown next to the field, and written as how to fix it?
- Are entered values kept after a validation error, a failure and going back?
- Can the user retry after a network or server failure without starting over?
- What happens offline, on timeout, or when the session expires mid-task?

## Empty states (`empty-state`)
- Does every list or search have an empty state that explains why and offers a next action?
- Is a first-time empty state different from a "nothing matched" empty state?

## Consistency (`consistency`)
- Same action, same label and same position across screens.
- Same term for the same thing everywhere (for example, "모임" vs "스터디").

## Copy (`copy`)
- Buttons use clear verbs ("신청 보내기", not "확인").
- No internal jargon, codes or English mixed into Korean UI without reason.

## Accessibility (`accessibility`)
- Tap targets are large enough, and controls are not icon-only without a label.
- Images that carry meaning have a text alternative. Color is never the only signal of state or error.
- Form fields have labels, and focus order follows reading order.

## Trust and safety (`other`)
- Personal data says why it is collected and who sees it, at the point of collection.
- Destructive or irreversible actions ask for confirmation and say what will be lost.
- Payment and account changes show the final result before committing.

## Policy gaps
Anything that needs a business decision goes into `decisions`, not `issues`. Examples: approval rules, refund conditions, retention, limits.
