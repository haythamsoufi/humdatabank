# Notification Sounds Directory

This directory contains audio files for notification sounds.

## Required Files

### notification.mp3
A short, pleasant notification sound that plays when new notifications arrive (if user has sound enabled in preferences).

**Requirements:**
- Format: MP3
- Duration: 0.5 - 2 seconds
- File size: < 50KB
- Volume: Moderate (will be played at 50% volume in code)

**Recommended Sources:**
1. Create your own using audio editing software
2. Use royalty-free sounds from:
   - https://freesound.org/
   - https://mixkit.co/free-sound-effects/
   - https://www.zapsplat.com/

**Example sounds to search for:**
- "gentle notification"
- "soft bell"
- "message pop"
- "notification chime"

## Adding the Sound File

1. Download or create a suitable notification sound
2. Convert to MP3 format if necessary
3. Rename to `notification.mp3`
4. Place in this directory (`Backoffice/app/static/sounds/`)
5. Test by enabling sound in notification preferences

## Browser Compatibility

MP3 is supported in all modern browsers:
- Chrome: Yes
- Firefox: Yes
- Safari: Yes
- Edge: Yes
- Mobile browsers: Yes

## Note

The sound will only play if:
1. User has enabled sound in notification preferences
2. New notifications arrive while user is actively viewing the site
3. Browser allows autoplay (most modern browsers do for user-initiated actions)
4. The notification count increases from previous check

If no sound file is present, the feature will fail gracefully without errors.
