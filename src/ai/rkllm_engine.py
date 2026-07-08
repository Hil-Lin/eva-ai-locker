"""
RKLLM Engine - 最小改动版本（基于成功的 test_full.py）
"""
import ctypes
import os
import time
import threading

class RKLLMEngine:
    def __init__(self, model_path: str):
        self.model_path = model_path
        self.lib_path = "/opt/smart-locker/demo/lib/librkllmrt.so"
        self._handle = None
        self._lib = None
        self._response_buffer = []
        self._response_complete = threading.Event()

        # 结构体定义
        class RKLLMExtendParam(ctypes.Structure):
            _fields_ = [
                ("base_domain_id", ctypes.c_int32),
                ("reserved", ctypes.c_uint8 * 112),
            ]

        class RKLLMParam(ctypes.Structure):
            _fields_ = [
                ("model_path", ctypes.c_char_p),
                ("max_context_len", ctypes.c_int32),
                ("max_new_tokens", ctypes.c_int32),
                ("top_k", ctypes.c_int32),
                ("top_p", ctypes.c_float),
                ("temperature", ctypes.c_float),
                ("repeat_penalty", ctypes.c_float),
                ("frequency_penalty", ctypes.c_float),
                ("presence_penalty", ctypes.c_float),
                ("mirostat", ctypes.c_int32),
                ("mirostat_tau", ctypes.c_float),
                ("mirostat_eta", ctypes.c_float),
                ("skip_special_token", ctypes.c_bool),
                ("is_async", ctypes.c_bool),
                ("img_start", ctypes.c_char_p),
                ("img_end", ctypes.c_char_p),
                ("img_content", ctypes.c_char_p),
                ("extend_param", RKLLMExtendParam),
            ]

        class RKLLMResultLastHiddenLayer(ctypes.Structure):
            _fields_ = [
                ("hidden_states", ctypes.POINTER(ctypes.c_float)),
                ("embd_size", ctypes.c_int),
                ("num_tokens", ctypes.c_int),
            ]

        class RKLLMResult(ctypes.Structure):
            _fields_ = [
                ("text", ctypes.c_char_p),
                ("token_id", ctypes.c_int32),
                ("last_hidden_layer", RKLLMResultLastHiddenLayer),
            ]

        class RKLLMInput(ctypes.Structure):
            _fields_ = [
                ("input_type", ctypes.c_int),
                ("prompt_input", ctypes.c_char_p),
            ]

        class RKLLMInferParam(ctypes.Structure):
            _fields_ = [("mode", ctypes.c_int)]

        self.RKLLMParam = RKLLMParam
        self.RKLLMInput = RKLLMInput
        self.RKLLMInferParam = RKLLMInferParam
        self.CALLBACK_TYPE = ctypes.CFUNCTYPE(None, ctypes.POINTER(RKLLMResult), ctypes.c_void_p, ctypes.c_int)

    def init(self) -> bool:
        self._lib = ctypes.CDLL(self.lib_path)

        self._lib.rkllm_createDefaultParam.restype = self.RKLLMParam
        self._lib.rkllm_init.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.POINTER(self.RKLLMParam),
            self.CALLBACK_TYPE,
        ]
        self._lib.rkllm_init.restype = ctypes.c_int

        self._lib.rkllm_run.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(self.RKLLMInput),
            ctypes.POINTER(self.RKLLMInferParam),
            ctypes.c_void_p,
        ]
        self._lib.rkllm_run.restype = ctypes.c_int

        self._lib.rkllm_destroy.argtypes = [ctypes.c_void_p]
        self._lib.rkllm_destroy.restype = ctypes.c_int

        param = self._lib.rkllm_createDefaultParam()
        param.model_path = self.model_path.encode('utf-8')
        param.max_new_tokens = 256
        param.max_context_len = 2048
        param.temperature = 0.1
        param.skip_special_token = True
        param.is_async = False
        param.extend_param.base_domain_id = 0

        def callback(result_ptr, userdata, state):
            if state == 0:  # RKLLM_RUN_NORMAL
                if result_ptr and result_ptr.contents.text:
                    try:
                        text = result_ptr.contents.text.decode('utf-8', errors='replace')
                        self._response_buffer.append(text)
                    except:
                        pass
            elif state == 2:  # RKLLM_RUN_FINISH
                self._response_complete.set()
            elif state == 3:  # RKLLM_RUN_ERROR
                self._response_complete.set()

        self._callback_func = self.CALLBACK_TYPE(callback)
        self._handle = ctypes.c_void_p()
        ret = self._lib.rkllm_init(ctypes.byref(self._handle), ctypes.byref(param), self._callback_func)
        return ret == 0

    def generate(self, prompt: str) -> str:
        self._response_buffer = []
        self._response_complete.clear()

        # Qwen2 聊天模板格式
        full_prompt = (
            "<|im_start|>system\n"
            "You are Qwen, created by Alibaba Cloud. You are a helpful assistant.<|im_end|>\n"
            "<|im_start|>user\n"
            + prompt +
            "<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

        rkllm_input = self.RKLLMInput()
        rkllm_input.input_type = 0
        rkllm_input.prompt_input = full_prompt.encode('utf-8')

        infer_param = self.RKLLMInferParam()
        infer_param.mode = 0

        t0 = time.time()
        self._lib.rkllm_run(self._handle, ctypes.byref(rkllm_input), ctypes.byref(infer_param), None)
        self._response_complete.wait(timeout=30)
        elapsed = time.time() - t0

        response = ''.join(self._response_buffer)
        print(f"[RKLLM] 推理耗时: {elapsed:.2f}s")
        return response

    def shutdown(self):
        if self._handle and self._lib:
            self._lib.rkllm_destroy(self._handle)


if __name__ == "__main__":
    engine = RKLLMEngine("/opt/smart-locker/models/Qwen2-1.5B_W8A8_RK3588.rkllm")
    if engine.init():
        print("✅ 初始化成功")
        response = engine.generate("你好")
        print(f"回复: {response}")
        engine.shutdown()
    else:
        print("❌ 初始化失败")
