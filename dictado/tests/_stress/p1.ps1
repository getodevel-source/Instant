Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = -1
$s.SetOutputToWaveFile("C:\\PROYECTOS\\Instant\\dictado\\tests\\_stress\\p1.wav")
$s.Speak("The quick brown fox jumps over the lazy dog near the river bank.")
$s.Dispose()
