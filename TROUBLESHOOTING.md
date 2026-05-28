# Protocol Bot - Troubleshooting Guide

## Issue: "Conflict: terminated by other getUpdates request"

This is the most common issue. It happens when:
- Multiple bot instances are running
- Previous instance didn't close cleanly
- Telegram's servers still think there's an active connection

### Solution:

**Option 1: Use the Helper Script (Recommended)**
```bash
start_bot.bat
```

**Option 2: Manual Steps**
1. Close ALL terminal windows
2. Run: `taskkill /F /IM python.exe`
3. **Wait 30-60 seconds** (this is critical!)
4. Run: `python main.py`

### Why the wait is important:
Telegram's API needs time to recognize the previous connection is closed. If you restart too quickly, you'll get the same error.

## Issue: Bot doesn't respond to commands

### Check:
1. Is the bot running? Look for "Bot is running..." in terminal
2. Did you send the command to the correct bot? (@NewConvertsBot)
3. Is there an error in the terminal?

### Solution:
- Restart the bot using `start_bot.bat`
- Send `/start` to verify it's working

## Issue: "No members found in HOSPITALITY MEMBERS.xlsx"

### Check:
1. Is `HOSPITALITY MEMBERS.xlsx` in the root directory?
2. Are the headers exactly: `NAME`, `COLLEGE`, `HALL` (all caps)?
3. Is there data in the rows below the headers?

### Solution:
- Verify file location and format
- Check for typos in column headers

## Issue: Reports not generating

### Check:
1. Did you complete all the prompts?
2. Is there a `data/` folder?
3. Do you have write permissions?

### Solution:
- The bot creates `data/` automatically
- Check file permissions in the project folder
- Look for error messages in the terminal

## Best Practices

1. **Only run ONE instance** of the bot at a time
2. **Use `start_bot.bat`** instead of running `python main.py` directly
3. **Wait before restarting** if you encounter errors
4. **Keep HOSPITALITY MEMBERS.xlsx updated** with current member information
5. **Check the terminal** for error messages if something doesn't work

## Getting Help

If you see an error message:
1. Copy the full error from the terminal
2. Check what command you were running
3. Verify your Excel file format
4. Make sure only one instance is running
