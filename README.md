
# About

- RapidStream takes in a Vivado HLS dataflow design, then generates a fully placed and routed checkpoint.

- RapidStream adopts a divide-and-conquer approach at the behavior level that achieves 5-7X speed up compared to the vanilla Vivado flow.

- The key insight of RapidStream is to utilize the fact that we can additionally pipeline the FIFO connections, which create additional flexibility for split placement and routing without timing degradation.

- More details could be found in our FPGA 2022 paper that is also included in the repo:

```
@inproceedings{guo22rapidstream,
  title={RapidStream: Parallel Physical Implementation of FPGA HLS Designs},
  author={Licheng Guo, Pongstorn Maidee, Yun Zhou, Chris Lavin, Jie Wang, Yuze Chi, Weikang Qiao, Alireza Kaviani, Zhiru Zhang, Jason Cong},
  year={2022},
  booktitle={Proceedings of the 2022 ACM/SIGDA International Symposium on Field-Programmable Gate Arrays (FPGA '22)}
}
```

# Highlights

- This figure shows (1) the number of active cores in a vanilla Vivado flow, (2) Vivado runtime V.S. the number of threads.

<img src=https://user-images.githubusercontent.com/32432619/143661683-f79d0c68-f47e-44d1-a9c1-ac4b6ad960a1.png alt="alt text" width=400>

- In comparison, this figure shows the statistics of RapidStream:

<img src=https://user-images.githubusercontent.com/32432619/143661676-f44333c2-d3ae-4bdb-9309-b46dae88f370.png alt="alt text" width=400>

- Here is the runtime and frequency comparison between RapidStream and Vivado:

<img src=https://user-images.githubusercontent.com/32432619/143661688-4ec558cd-d812-4616-bb01-4034220ba517.png alt="alt text" width=375>

- To achieve such improvement, RapidStream go through the following steps. 
    - The key is to make good use of the pipelining flexibility of dataflow designs.

![][image-steps]

- This figure shows the input and output of each phase:
    - Phase 1 floorplans and re-builds the hierarchy of the HLS-generated RTL, then adds pipelining.
    - Phase 2 places and routes each island in parallel while ensuring the interface of neighbor islands align.
    - Phase 3 stitch the islands together and route the inter-island nets

![][image-three-phase]


# Install

- The script has been tested on ubuntu 18.04.

- Python 3.6+ required.

- Please install on EVERY server that will be used for the distributed execution.

```
bash install.sh
```


- Obtain an auto-issued Gurobi license at https://www.gurobi.com/downloads/end-user-license-agreement-academic/
    

- Update `GRB_LICENSE_FILE` in `${RAPID_STREAM_PATH}/rapidstream_setup.sh` to point to your license file


- Install Xilinx Vivado HLS 2019.2 or 2020.1

- Install Xilinx Vivado

- source `${RAPID_STREAM_PATH}/rapidstream_setup.sh`


# Examples

There are 6 examples to demonstrate the flow. Each one includes:

- The HLS source code and the HLS synthesis project.

- A reference configuration file.

- A one-click script to run the whole flow. 

- Note that you need to update the environment variables in the script.

- You should edit the `SERVER_LIST` variable to include the IP address/acronym of your server fleet. You could use whatever number of servers you want. 

  - If you only provide 1 server, then all parallel tasks will be performed on it, which will use lots of memory. We recommend that you should have at least 256 GB of memory to run everything on 1 server.

  - In our experiments, we distribute the workloads to 4 servers, each with the 56-core Inter Xeon E5-2680 v4 CPU at 2.40GHz and 128 GB of memory. 

- To help you reproduce the results as in the paper, we include a reference floorplanning result as this step is non-deterministic. 
  - To re-run the Phase 1 floorplanning process from scratch, delete the "ResultReuse" field in the JSON configuration file.


# File Organizations

- `examples` provide six benchmarks and one-click script to run RapidStream.

- `python/rapidstream` contains the main implementation of RapidStream.
  - `python/rapidstream/FE` corresponds to the front end transformation on the HLS-generated RTL (Phase 1 in the paper)
  - `python/rapidstream/BE` corresponds to the back end parallel implementation (Phase 2, 3 in the paper)  

- `java/` contains tools implemented in RapidWright, including the checkpoint stitcher for Phase 3 (`java/mergeDCP.java`
)

- `bash/` include scripts to glue together various part of the flow. 
  - `bash/run_back_end.sh` is the main flow of Phase 2 and 3.

# Next Step

- Currently RapidStream results cannot run on board as we are not compatible with the Vitis workflow. 

- The next step is to develop a customized IO shell so that the RapidStream bitstream could communicate with the host.


[image-vivado-cpu]:https://user-images.githubusercontent.com/32432619/143661683-f79d0c68-f47e-44d1-a9c1-ac4b6ad960a1.png

[image-rapidstream-cpu]:https://user-images.githubusercontent.com/32432619/143661676-f44333c2-d3ae-4bdb-9309-b46dae88f370.png

[image-comparison]:https://user-images.githubusercontent.com/32432619/143661688-4ec558cd-d812-4616-bb01-4034220ba517.png

[image-steps]:https://user-images.githubusercontent.com/32432619/143661628-dfe9a02d-92e6-4a71-b738-96477a210202.png

[image-three-phase]:https://user-images.githubusercontent.com/32432619/143661651-33aa492a-24c4-42c5-b72c-43d2a8fa8ecd.png
