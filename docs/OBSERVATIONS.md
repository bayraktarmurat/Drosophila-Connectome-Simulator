## Observations

- Created by me to record every experiment and observation and make informed judgements.

## Observation 1.x 
**I ablated all input (sensory) neurons expect LB3c_L (78240) and stimulated that neuron from 1Hz -> 100Hz as force spikes for 1000ms with stimuli starting from 50ms to 800ms.** 

- The first interneuron fired was GNG038_L (21746) at 494ms, followed by GNG038_R at 750ms and GNG132_L at 751ms with the actual cascade beginning with DNge023_L at 756ms with ~15 interneurons firing until first output neuron fires around 762ms (MN2Da_L).

- I noticed there are many LB3c_L neurons and the one I kept alive was with id 78240.
 **I ablated all except all 11 LB3c_L neurons now with the same configuration.**
- First interneuron fired was GNG215_L 172ms and GNG038_LR at 173ms. After the very first interneurons fired  those were nearly fired at the same time:GNG042_L -> GNG042_R and GNG524_L(285ms).

- just after 0-1 ms after those fired almost simultaneously: DNge023_L (again!) and GNG029_R. After that the frequent spikes start among interneurons. In this simulation the first output generates again in MN2Da_L in 290ms. I observed that stimulating all LB3c_L neurons, the whole network goes rouge again after DNge023_L (285ms - 286ms) ((*)also possibly GNG029_R, playing similar key role?) but the first output now first again at MN2Da_L ~113ms after GNG038_L and GNG038_R (it was 268ms after GNG038_L and 12ms after GNG038_R at previous sim.)

- The first output was 712ms after the first input stimulation, 268ms after first interneuron firing in the first simulation; 240ms after first input, 118ms after first interneuron firing in the second simulation.

- From the very first miliseconds the input neurons constantly fired. Dataset says that LB3c are cholinergic (exitatory to the interneurons and among themselves). In average, their most outputs are to GNG038, GNG215 followed by GNG042 and GNG132. GNG neurons are mostly inhibitory to LB3c_L neurons. GBG132_L (18474) has most synapses (219) with DNge023_L (29086).

- GNG048_R (14210) has inhibitory effect on GNG042_R (15734).

**Repeated with ablated neuronsin the 2nd simulation but at constant firing.**
- First output is now at 21ms. I observed that it follows the same interneurons but faster.

**Judgements**

- I can verify temporal summation by running the chosen simulation in ramping and constant modes. 
- I can verify spatial summation by comparing the first and the second simulation.
- Since the connectome is wired with a constant synaptic potential through all the connectome, its not safe to verify that one input neuron is able to fire a large network of interneurons as to verify that that one neuron LB3c (78240) is connected to a common interneuron that can start this process.


- No synapses between GNG038_R. One synapse between GNG038_L (21746) and GNG132_L (18474).
- A synapse exists between GNG132_L (18474) and  DNge023_L (29086).