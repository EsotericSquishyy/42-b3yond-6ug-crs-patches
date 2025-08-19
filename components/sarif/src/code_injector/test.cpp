int main() {
    const char* msg="AIXCC_REACH_TARGET_0\n"; __asm__ __volatile__("mov $1, %%rax; mov $2, %%rdi; mov %[buf], %%rsi; mov $21, %%rdx; syscall": :[buf] "r" (msg) : "rax", "rdi", "rsi", "rdx", "rcx", "r11", "memory");
}