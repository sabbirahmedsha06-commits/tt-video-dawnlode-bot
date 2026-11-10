# Streamly Telegram Bot

## GitHub + Render deployment

1. Upload all files in this folder to your GitHub repository.
2. Create a Render Blueprint or Python Web Service.
3. Set `TOKEN` and `ADMIN_ID` in Render Environment Variables.
4. Deploy. The health endpoint is `/healthz`.

## Important

- The original TikWM/SnapTik resolver and original download flow are preserved unchanged.
- The existing reply-keyboard layout is preserved; each button now has a Telegram Bot API 9.4 color style.
- The Owner reply button remains in its original position. Pressing it displays a direct green URL button.
- Data is stored in `streamly_data.json`; Render Free local storage may be ephemeral.
- The bot token that was present in the earlier source should be revoked in BotFather. Set the newly generated token only in Render Environment Variables.
