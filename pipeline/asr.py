import sherpa_onnx, wave, numpy as np, json, sys, os
M=os.path.join(os.path.dirname(os.path.abspath(__file__)),'models','sherpa-onnx-zipformer-korean-2024-06-24')
r=sherpa_onnx.OfflineRecognizer.from_transducer(encoder=f'{M}/encoder-epoch-99-avg-1.int8.onnx',decoder=f'{M}/decoder-epoch-99-avg-1.onnx',joiner=f'{M}/joiner-epoch-99-avg-1.int8.onnx',tokens=f'{M}/tokens.txt',num_threads=4)
w=wave.open(sys.argv[1]); sr=w.getframerate(); x=np.frombuffer(w.readframes(w.getnframes()),np.int16).astype(np.float32)/32768
for s in json.load(open(sys.argv[2])):
    st=r.create_stream(); st.accept_waveform(sr, x[int(s['start']*sr):int(s['end']*sr)]); r.decode_stream(st)
    print('원문:',s['text']); print('인식:',st.result.text); print()
