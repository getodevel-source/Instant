Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = -1
$s.SetOutputToWaveFile("C:\\PROYECTOS\\Instant\\dictado\\tests\\_stress\\p2.wav")
$s.Speak("Pack my box with five dozen liquor jugs for the long journey.")
$s.Dispose()
