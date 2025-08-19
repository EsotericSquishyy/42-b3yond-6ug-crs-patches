from langchain_core.messages import HumanMessage, AIMessage, AnyMessage
from seedgen2.graphs.cotbot import CoT
import logging

from seedgen2.presets import SeedGen2GenerativeModel

logging.basicConfig(level=logging.INFO)


prompt = """
A farmer needs to cross a river with two chickens. The boat only has room for one human and two animals. What is the smallest number of crossings needed for the farmer to get across with the two chickens?
"""


print("COT result:")
model = CoT(model=SeedGen2GenerativeModel().model,
            json_model=SeedGen2GenerativeModel().json_model)
print(model.invoke([HumanMessage(content=prompt)]).content)

print("Chain-of-thought:")
print(model.get_chain_of_thought())

print("Normal result:")
model = SeedGen2GenerativeModel().model
print(model.invoke([HumanMessage(content=prompt)]).content)
