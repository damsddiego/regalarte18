# Sales Commission OMAX - Enhanced Version

This module extends the functionality of the Sales Commission OMAX module to allow commission calculations based on the number of days an invoice has been outstanding.

## New Features

### Commission by Days
The module now allows you to configure different commission percentages based on the number of days between the invoice date and due date. The ranges are fully configurable per commission using the "Day Ranges" table, so you can define custom boundaries (e.g., 0-15, 16-45, 46-120, 121+) and the commission percentage for each range.

## Configuration

1. Go to Sales > Sales Commission > Sales Commission
2. Create a new commission or edit an existing one
3. Select "Standard" as the Commission Type
4. Check the "Commission by Days" box
5. Add one or more entries in the "Day Ranges" table, specifying the minimum and maximum number of days (leave max empty for an open-ended range) and the commission percentage to apply when the invoice falls into that range.

## How It Works

When an invoice is validated or paid (depending on your commission configuration), the system will:
1. Calculate the difference in days between the invoice date and due date
2. Apply the corresponding commission percentage based on the day range
3. Generate the commission analysis line with the calculated amount

## Example

If you configure ranges like:
- 0-30 days: 5%
- 31-60 days: 3%
- 61-90 days: 2%
- 90+ days: 1%

And an invoice has a due date 45 days after the invoice date, the system will apply a 3% commission. You can change the ranges and percentages to match your business rules.

## Notes

- The "Commission by Days" feature only works with "Standard" commission type
- If "Commission by Days" is enabled, the standard commission percentage field is hidden
- At least one day range must be configured when "Commission by Days" is enabled