### General Information

* **Environment name:** `[name of the environment]`
* **Language:** `[CUDA, CUTLASS, Pallas, etc]`
* **Category:** `[ML training kernels, ML inference kernels, scientific computing, open-source libraries, etc]`
* **Hardware required:** `[we recommend starting with single-device kernels for now, we can move to distributed kernels later]`

### Design & Scope

* **Description of kernels:**
  * *What will the tasks in this environment ask the student to do? What will these tasks have in common?*
* **Motivation:**
  * *What are we hoping to teach the student? What is interesting about the tasks in this environment?*
* **Task diversity:**
  * *What sort of tasks are you planning to build? What makes the tasks in this environment diverse?*

### Technical Implementation

* **Interface:**
  * *What interface will the student need to implement? How will the interface differ between tasks?*
* **Baseline:**
  * *Describe, at a high level, what the baseline will be for the tasks in this environment. What language will it be implemented in? Will it be implemented by hand by one of us, or will it be taken from an existing library? How will the reviewer determine that the implementation is correct?*
* **Best practices for timing:**
  * *What are best practices for timing kernels in this language and on this hardware?*

### Reward Hacking & Validation

* **Reward hacking via high-level libraries:**
  * *Are there high-level libraries the student could use to reward hack? If so, how will the interface prevent this? If not, why not? If the interface can’t prevent it, how will it be prevented?*
* **Reward hacking via quantization:**
  * *Is using lower precision a possible reward hacking vector? If not, why not? If so, how will the values of rtol/atol be chosen to prevent both reward hacking and reward denial? How do you plan to convince the reviewer(s) that the values of rtol/atol prevent reward hacking and reward denial?*
* **Other reward hacking vectors:**
  * *What other reward hacking vectors might arise? (e.g., dynamic loading, monkey-patching).*

### Scoring & Evaluation

* **Scoring script:**
  * *Describe how the scoring script for the environment will work. What will it do?*
* **Scoring calibration:**
  * *How do you expect the scores to be calibrated? What will a score of 0.5 represent? What will a score of 0.2 represent? (This can change later, but we want an initial sense of calibration).*

### Resources

* **Instruction template:**
  * *Write the instruction template as a python f-string. (See examples for reference).*
* **Documentation:**
  * *What documentation should the student have access to?*

---

# Task List

Each environment should consist of many tasks. Tasks on different topics should be separated into different environments. For each task planned in this environment, please fill out the template below.

### [Task Name]

* **Description:** `[Description of the kernel to be optimized. Why is it interesting?]`
* **Hyperparameters:** `[What shapes, dtypes, etc. will be chosen?]`
* **Axes of Variation:** `[Are there any axes of variation that will be varied to create additional tasks? If so, which axes will be varied and how many tasks will be created?]`
