// SPDX-License-Identifier: MIT

pragma solidity >=0.7.0 <0.9.0;

contract EasyTender {
    enum TenderState { Open, Played, Executed }
    enum ContractState { Aggreed, Executed, Cancelled }
    enum OfferState { New, Rejected, Accepted }

    mapping(bytes32 => Tender) tenders;
    mapping(bytes32 => TenderContract) contracts;

    uint256 voteReward = 10;

    struct Tender {
        address sender;
        string text;
        TenderState state;

        uint256 voteSize;
        uint256 offerSize;

        mapping(uint256 => Vote) votes;
        mapping(uint256 => Offer) offers;
    }

    struct Offer {
        address sender;
        string text;
        uint256 price;
        OfferState state;
    }

    struct Vote {
        address sender;
        bool desicion;
    }

    struct TenderContract {
        bytes32 tenderId;
        uint256 offerIndex;
        ContractState state;
    }

    // Owner flow - starting and accepting tender, pays for contract execution
    function newTender(string calldata text) public returns (bytes32 tenderId) {
        tenderId = keccak256(abi.encode(msg.sender, text));
       
        Tender storage tender = tenders[tenderId];
        tender.sender = msg.sender;
        tender.text = text;
        tender.state = TenderState.Open;
    }

    function aceptOffer(bytes32 tenderId, uint256 offerIndex) public returns (bytes32 contractId) {
        Tender storage tender = tenders[tenderId];
        tender.offers[offerIndex].state = OfferState.Accepted;
        tender.state = TenderState.Played;
        contractId = keccak256(abi.encode(msg.sender, tenderId, offerIndex));
        TenderContract storage tenderContract = contracts[contractId];
        tenderContract.tenderId = tenderId;
        tenderContract.offerIndex = offerIndex;
        tenderContract.state = ContractState.Aggreed;
    }

    function rejectOffer(bytes32 tenderId, uint256 offerIndex) public {
        Tender storage tender = tenders[tenderId];
        tender.offers[offerIndex].state = OfferState.Rejected;
    }

    // // Participant flow - offering and executing contract
    function sendOffer(bytes32 tenderId, string calldata text, uint256 price) public {
        Tender storage tender = tenders[tenderId];
        tender.offers[tender.offerSize++] = Offer(msg.sender, text, price, OfferState.New);
    }

    function executeContract(bytes32 contractId) public {
        TenderContract storage tenderContract = contracts[contractId];
        tenderContract.state = ContractState.Executed;
        Tender storage tender = tenders[tenderContract.tenderId];
        tender.state = TenderState.Executed;
        Offer memory offer = tender.offers[tenderContract.offerIndex];
        address payable beneficiary = payable(offer.sender);
        beneficiary.transfer(offer.price);
    }

    // // Researchers flow - voting for reward
    function vote(bytes32 tenderId, bool decision) public {
        Tender storage tender = tenders[tenderId];
        tender.votes[tender.voteSize++] = Vote(msg.sender, decision);

        payable(msg.sender).transfer(voteReward);
    }
    // fun vote(OfferVote) return Reward
    // fun vote(ParticipantVote) return Reward
    // fun vote(OwnerVote) return Reward
