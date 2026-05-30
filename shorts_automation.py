def generate_voice(text, audio_path, ass_path, time_offset=0.0):
    """Generate Hindi TTS using Google Cloud Text-to-Speech (FREE tier)."""
    import os
    from google.oauth2 import service_account
    
    # Try to use service account credentials from environment variable first
    credentials_json = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if credentials_json and os.path.exists(credentials_json):
        credentials = service_account.Credentials.from_service_account_file(credentials_json)
        client = texttospeech.TextToSpeechClient(credentials=credentials)
    else:
        # Fall back to default credentials (Application Default Credentials)
        client = texttospeech.TextToSpeechClient()
    
    synthesis_input = texttospeech.SynthesisInput(text=text)
    
    # Use Hindi voice - Neural (faster, better quality) or Standard
    voice = texttospeech.VoiceSelectionParams(
        language_code="hi-IN",
        name="hi-IN-Neural2-A",  # Female Hindi voice
        ssml_gender=texttospeech.SsmlVoiceGender.FEMALE,
    )
    
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        pitch=0.0,
        speaking_rate=1.0,
    )
    
    request = texttospeech.SynthesizeSpeechRequest(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
        enable_time_pointing=[texttospeech.SynthesizeSpeechRequest.TextToSpeechFeature.SSML_DIALECT],
    )
    
    response = client.synthesize_speech(request=request)
    
    # Save audio file
    with open(audio_path, "wb") as out:
        out.write(response.audio_content)
    
    print(f"[voice] Ses olusturuldu -> {Path(audio_path).name}")
    
    # Generate simple subtitle timing from character breakdown
    # Approximate: divide text duration by character count
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    duration = float(out.stdout.strip())
    
    # Simple word timing: distribute duration across words
    words = text.split()
    word_duration = duration / len(words) if words else 0
    
    cues = []
    current_time = 0.0
    for word in words:
        cues.append(_WordCue(word, current_time, current_time + word_duration))
        current_time += word_duration
    
    _build_ass(cues, time_offset, ass_path)
    
    print(f"[voice] {duration:.1f}s ses uretildi -> {audio_path.name}")
    return duration
