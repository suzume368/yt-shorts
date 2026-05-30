def generate_voice(text, audio_path, ass_path, time_offset=0.0):
    """Generate Hindi TTS using Microsoft Edge TTS (FREE, no API key needed)."""
    import asyncio
    import edge_tts

    async def _synthesize():
        communicate = edge_tts.Communicate(text, voice="hi-IN-SwaraNeural")
        await communicate.save(str(audio_path))

    asyncio.run(_synthesize())

    # Get duration via ffprobe
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(out.stdout.strip())

    # Distribute word timing evenly across duration
    words = text.split()
    word_duration = duration / len(words) if words else 0
    cues = []
    current_time = 0.0
    for word in words:
        cues.append(_WordCue(word, current_time, current_time + word_duration))
        current_time += word_duration

    _build_ass(cues, time_offset, ass_path)
    print(f"[voice] {duration:.1f}s audio ready -> {audio_path.name}")
    return duration
