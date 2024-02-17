Model:

Owner
- address

Researcher
- address

Participant
- address

Tender
- TenderOwner
- Condition

Condition
- ifMeets

TenderVote
- Tender
- ConditionVote

ConditionVote
- Condition
- desicion

ParticipantVote
- Participant
- decision

OwnerVote
- Owner
- decision

OfferVote
- Offer
- OfferConditionVote

OfferConditionVote
- OfferCondition
- decision

Offer
- Tender
- Participant
- ConditionOffer
- price

Reward
- amount

TenderContract
- Tender
- Offer

Payment 
- TenderContract
- isExecuted


// Owner flow - starting and aceepting tender, pays for contract execution
fun startTender(Tender) 

fun acceptOffer(Offer) return TenderContract

fun rejectOffer(Offer)


// Participant flow - offering and executing contract

fun sendOffer(Offer)

fun executeContract(TenderContract) return Payment


// Researchers flow - voting for reward

fun vote(TenderVote) return Reward

fun vote(OfferVote) return Reward

fun vote(ParticipantVote) return Reward

fun vote(OwnerVote) return Reward


